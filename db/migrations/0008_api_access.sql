-- Restricted serving identity and shared admission control. No observation changes.
-- Passwords are provisioned separately and never appear in migrations.
-- LOGIN: the API connects AS this role (API_DATABASE_URL). Its password is set
-- out of band, so nothing secret enters the repository. Everything else is
-- withheld: it cannot create roles or databases, and cannot bypass RLS.
CREATE ROLE portal_api LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
ALTER ROLE portal_api SET statement_timeout = '5s';
ALTER ROLE portal_api SET lock_timeout = '1s';
ALTER ROLE portal_api SET idle_in_transaction_session_timeout = '10s';
GRANT USAGE ON SCHEMA public TO portal_api;

DO $$
DECLARE relation text;
BEGIN
  FOREACH relation IN ARRAY ARRAY['indicators', 'units', 'sources', 'datasets',
    'geographies', 'time_periods', 'releases', 'observations', 'ingestion_log']
  LOOP
    EXECUTE format('GRANT SELECT ON public.%I TO portal_api', relation);
    EXECUTE format('CREATE POLICY portal_api_read ON public.%I FOR SELECT TO portal_api USING (true)', relation);
  END LOOP;
END $$;

CREATE SCHEMA api_private;
REVOKE ALL ON SCHEMA api_private FROM PUBLIC;
GRANT USAGE ON SCHEMA api_private TO portal_api;
CREATE TABLE api_private.admission (
  id integer PRIMARY KEY CHECK (id = 1), minute bigint NOT NULL, requests integer NOT NULL
);
INSERT INTO api_private.admission VALUES (1, 0, 0);
CREATE TABLE api_private.clients (
  client text PRIMARY KEY CHECK (client ~ '^[a-f0-9]{64}$'),
  minute bigint NOT NULL, minute_requests integer NOT NULL,
  day bigint NOT NULL, day_requests integer NOT NULL, bytes bigint NOT NULL
);
CREATE INDEX clients_day ON api_private.clients (day);
CREATE TABLE api_private.leases (
  token uuid PRIMARY KEY, client text NOT NULL REFERENCES api_private.clients(client),
  day bigint NOT NULL, expires timestamptz NOT NULL
);
CREATE INDEX leases_client ON api_private.leases (client);
CREATE INDEX leases_expiry ON api_private.leases (expires);

-- Global lock first for BOTH functions: admission and settlement are atomic
-- across processes, workers and serverless instances, with no oversubscription.
CREATE FUNCTION api_private.reserve_access(p_client text, p_token uuid)
RETURNS TABLE (allowed boolean, retry_after integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE
  stamp bigint := floor(extract(epoch FROM clock_timestamp()));
  m bigint := stamp / 60;
  d bigint := stamp / 86400;
  c api_private.clients%ROWTYPE;
  global_requests integer;
BEGIN
  IF p_client !~ '^[a-f0-9]{64}$' OR p_token IS NULL THEN
    RAISE EXCEPTION 'Invalid admission identity';
  END IF;
  SELECT CASE WHEN minute = m THEN requests ELSE 0 END INTO global_requests
    FROM api_private.admission WHERE id = 1 FOR UPDATE;
  DELETE FROM api_private.leases WHERE expires <= clock_timestamp();
  DELETE FROM api_private.clients WHERE client IN (
    SELECT client FROM api_private.clients c0 WHERE day < d - 1
    AND NOT EXISTS (SELECT 1 FROM api_private.leases l WHERE l.client = c0.client) LIMIT 100
  );
  IF global_requests >= 360 OR (SELECT count(*) FROM api_private.leases) >= 12 THEN
    RETURN QUERY SELECT false, 5; RETURN;
  END IF;
  INSERT INTO api_private.clients VALUES (p_client, m, 0, d, 0, 0)
    ON CONFLICT (client) DO NOTHING;
  SELECT * INTO c FROM api_private.clients WHERE client = p_client FOR UPDATE;
  IF c.minute <> m THEN c.minute_requests := 0; END IF;
  IF c.day <> d THEN c.day_requests := 0; c.bytes := 0; END IF;
  IF c.minute_requests >= 120 THEN
    RETURN QUERY SELECT false, (60 - stamp % 60)::integer; RETURN;
  END IF;
  IF c.day_requests >= 2000 OR c.bytes + 524288 > 20971520 THEN
    RETURN QUERY SELECT false, (86400 - stamp % 86400)::integer; RETURN;
  END IF;
  IF (SELECT count(*) FROM api_private.leases WHERE client = p_client) >= 4 THEN
    RETURN QUERY SELECT false, 2; RETURN;
  END IF;
  UPDATE api_private.admission SET minute = m, requests = global_requests + 1 WHERE id = 1;
  UPDATE api_private.clients SET minute = m, minute_requests = c.minute_requests + 1,
    day = d, day_requests = c.day_requests + 1, bytes = c.bytes + 524288
    WHERE client = p_client;
  INSERT INTO api_private.leases VALUES (p_token, p_client, d, clock_timestamp() + interval '60 seconds');
  RETURN QUERY SELECT true, 0;
END $$;

CREATE FUNCTION api_private.finish_access(p_token uuid, p_bytes integer)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE lease api_private.leases%ROWTYPE;
BEGIN
  PERFORM id FROM api_private.admission WHERE id = 1 FOR UPDATE;
  DELETE FROM api_private.leases WHERE token = p_token RETURNING * INTO lease;
  IF FOUND THEN
    UPDATE api_private.clients SET bytes = greatest(0, bytes - 524288 + least(524288, greatest(0, p_bytes)))
      WHERE client = lease.client AND day = lease.day;
  END IF;
END $$;

REVOKE ALL ON ALL TABLES IN SCHEMA api_private FROM PUBLIC, portal_api;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA api_private FROM PUBLIC;
GRANT EXECUTE ON FUNCTION api_private.reserve_access(text, uuid),
  api_private.finish_access(uuid, integer) TO portal_api;
