-- Quota history may be discarded; warehouse data and ingestion roles are untouched.
DROP SCHEMA api_private CASCADE;
DO $$
DECLARE relation text;
BEGIN
  FOREACH relation IN ARRAY ARRAY['indicators', 'units', 'sources', 'datasets',
    'geographies', 'time_periods', 'releases', 'observations', 'ingestion_log']
  LOOP
    EXECUTE format('DROP POLICY portal_api_read ON public.%I', relation);
    EXECUTE format('REVOKE SELECT ON public.%I FROM portal_api', relation);
  END LOOP;
END $$;
REVOKE USAGE ON SCHEMA public FROM portal_api;
DROP ROLE portal_api;
