# Security and concurrency review — 2026-09-06

The application supports simultaneous read requests, but its current design does not establish a safe production traffic capacity. Expensive public requests can consume substantial memory and database resources, and overlapping ingestion runs have correctness hazards. Address the high-priority findings before increasing traffic or running ingestion jobs concurrently.

This was a repository-wide static review with focused manual tracing of the API, SQL migrations, ingestion and maintenance operations, frontend data handling, and deployment workflows. The inventory covered 266 tracked files, including 147 code/configuration files containing 27,301 lines. Large reference datasets were inventoried and scanned rather than audited for statistical accuracy. Application code and database contents were not modified. Only this report, the project-log entry, and local review artifacts were written.

## Status — updated 2026-09-07

This review is a point-in-time record; it is not edited as work lands. What has
been done against it so far:

| Finding | State |
| --- | --- |
| 1 — Unbounded requests and memory | **Fixed.** Every public query now asks for one row past a cap and refuses the overflow with an explanation (`api/policy.py`); responses are capped at 2 MB; seasonality takes its provenance from a one-row query instead of building the full series; the sparkline endpoint serves only the codes it is asked for. Caps were sized against live counts, so the widest real request (4,675 daily prices; a 753-municipality map; 6,777 breakdown cells) still succeeds. |
| 2 — API holds administrative privileges | **Ready, not yet applied.** `db/migrations/0008_api_access.sql` creates the read-only `portal_api` role; the API uses it as soon as `API_DATABASE_URL` is set, and warns while it is not. Requires an operator to create the role and its password. |
| 9 — Server identity not verified | **Partly fixed.** Connections are encrypted and the code verifies the server's identity automatically once Supabase's CA certificate is saved to `reference/supabase/prod-ca-2021.crt` — it is published only in the project dashboard. `verify-full` cannot work before that: Supabase signs its pooler with its own private CA, which no public bundle can check. |
| Connection pressure / slow failure | **Partly fixed.** Connections carry a 5s connect timeout, an 8s statement timeout, a 1s lock timeout, a 10s idle-in-transaction timeout, a `portal-api` application name, and are read-only by default. No pool yet. |
| Browser request amplification | **Partly fixed.** The browser client deduplicates in-flight requests, caches for 60s, caps itself at 3 concurrent requests, and times out at 25s. |
| Rate limiting / overload responses | **Built, off by default.** A shared allowance lives in `api_private` (migration 0008) and turns on with `API_CLIENT_HASH_KEY`. It costs two extra database round trips per request, so it is opt-in rather than the default on a free tier. |
| 3, 4, 5, 6, 7, 8, 10 | **Open.** Concurrency races, session termination, dependency upgrades, NRB promotion, tooltip escaping, CSV formulas, partial publication. |

## Evidence and limits

| Check | Result |
| --- | --- |
| Existing Python suite | 311 passed; one Starlette TestClient deprecation warning |
| Existing frontend suite | 4 passed |
| Synthetic concurrent API requests | Batches of 1, 10, 40, and 80 all returned HTTP 200 with the correct request's indicator |
| Large synthetic response | 76,747 observations produced 10,733,815 response bytes and approximately 125.9 MiB peak traced Python allocations |
| Seasonality probe | Returned one synthetic aggregate while also constructing the entire 76,747-row source series |
| Chart injection probe | Actual TrendChart formatter output caused a harmless JavaScript marker to execute in an isolated headless browser using ECharts; browser networking was blocked |
| CSV probe | Actual exporter preserved a text cell beginning `=1+1` as a formula-capable CSV cell |
| npm production dependency audit | Four affected packages: Next.js, ECharts, PostCSS, nanoid; three high and one moderate package-level ratings |
| Installed Python package audit | OSV checked 54 public packages; flagged pip 26.1.2, pytest 8.4.2, and sqlparse 0.5.5 |
| Tracked-file pattern scan | No matching private-key, GitHub-token, AWS-access-key, or JWT patterns; no Python eval/exec, shell-process, pickle-load, unsafe YAML-load, or archive-extraction calls found by the targeted AST scan |
| Configured database | Catalog-only queries in read-only transactions; no observation data read or changed |

The database findings concern the connection configured in this workspace. Production Vercel environment variables, WAF rules, pooler limits, and replica settings were not independently inspected. There was no public-site load test, no malicious production request, and no concurrent write experiment against the live database. The functional tests use fakes and do not exercise PostgreSQL transaction races. Secret scanning was pattern-based and limited to the current tracked tree, not all Git history. The Python audit describes the installed environment, not a reproducibly locked production environment.

Local verification scripts and JSON evidence are under `.cache/security-review/` (gitignored). They include `verify_offline.py`, `verify_frontend.cjs`, `scan_repository.py`, `audit_python.py`, and `check_db_readonly.py`. The database script explicitly uses read-only transactions and short timeouts. Its `configured_statement_timeout` records the original setting; the separate `defaults.statement_timeout=5000` is the temporary five-second limit imposed by the reviewer.

## Prioritized findings

### 1. High — Public requests can allocate unbounded data and memory

**Locations:** `api/repository.py:367`, `api/repository.py:404`, `api/main.py:349`, `api/main.py:440`, `web/lib/api.ts:74`.

`GET /v1/data` has no pagination, maximum row count, or date-range requirement. Omitting the optional breakdown filter retrieves all matching observations with `fetchall()`, creates another list of observation objects, and then creates response-model objects and JSON. The endpoint documents a real series size of 76,747 observations. A synthetic request at that documented size returned 10.7 MB and used approximately 126 MiB of traced Python memory, excluding PostgreSQL and native-driver allocations. This is a scale demonstration, not a measurement of today's production rows or process RSS.

`GET /v1/data/seasonality` first computes compact aggregates but then calls unfiltered `get_series()` just to obtain provenance. It therefore pays the full-series cost even when its response is tiny. Spark queries likewise retrieve historical data and only keep their final 16 points in Python. Geography queries fetch historical periods before selecting the newest in Python.

No application rate limiter, bounded admission queue, shared result cache, or response caching policy was found. Browser requests explicitly use `cache: "no-store"`. Ordinary bursts and repeated expensive anonymous requests can exhaust resources or cause timeouts. External hosting protections may reduce exposure, but they do not correct the per-request cost.

**Fix:** Add bounded date/range pagination; provide a separate controlled bulk-export path. Obtain provenance with a small metadata query. Select the latest periods and spark points in SQL. Cache public results by normalized query and release, deduplicate in-flight requests, and add admission/rate limits with defined overload responses.

### 2. High — The API's configured database identity has administrative privileges

**Locations:** `api/main.py:61`, `api/repository.py:257`, `.env.example:8`.

The API takes the same `DATABASE_URL` convention used by migrations and ingestion and passes it directly to psycopg. Read-only Python methods do not restrict the database role.

The configured connection was confirmed to own the warehouse tables, have INSERT/UPDATE/DELETE privileges, and have CREATEROLE, CREATEDB, and BYPASSRLS. It is not a PostgreSQL superuser. RLS is enabled on the inspected public tables, but this identity bypasses it. A compromise of the API process or its database credential would therefore have a much larger impact than reading public statistics. This finding does not establish an existing remote route that performs arbitrary SQL.

**Fix:** Give the API a dedicated login with SELECT only on the required tables or views. Keep migration, ingestion, and storage credentials separate. Remove role/database creation and RLS-bypass privileges from the serving identity. Read-only transactions are useful additional protection; grants are the actual authorization boundary.

### 3. High — The latest-observation invariant is unsafe under concurrent writes

**Locations:** `db/migrations/0003_observations.sql:34`, `db/migrations/0003_observations.sql:48`, `ingestion/worldbank/pipeline.py:265`, `.github/workflows/ingest.yml:48`.

The AFTER INSERT trigger marks other visible versions of a cell as no longer latest. There is no unique constraint restricting each logical cell to one `is_latest=true` row. The unique constraint includes `release_id`, so two runs creating different releases do not conflict on that constraint. The live catalog confirmed these indexes match the migration, and the configured isolation level is READ COMMITTED.

A concrete unsafe interleaving is two transactions inserting the first observation for the same indicator/geography/period/breakdown under different releases before either commits. Each trigger cannot see the other's uncommitted insert; both can commit as latest. Existing-cell updates also require serialization and retry handling. The World Bank loader compounds this by reading its `latest` snapshot before a potentially long harvest, then writing based on that stale snapshot. PostgreSQL documents that READ COMMITTED does not expose another transaction's uncommitted rows. [PostgreSQL transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html).

The World Bank and NRB workflow jobs have no concurrency group. Only Kalimati has one, and a GitHub concurrency group does not coordinate local processes with CI.

**Fix:** Serialize publication for each dataset or logical cell using database-backed locking appropriate to the pooler's mode, re-read latest values inside that protected transaction, and enforce uniqueness of the current version. Redesign the trigger/publication sequence together with that constraint and retry conflicts; adding an index alone can turn the race into failed ingestions. Test two independent database connections, including retries and out-of-order releases.

### 4. High — Cleanup can terminate healthy API and ingestion sessions

**Locations:** `ingestion/worldbank/pipeline.py:127`, `scripts/nrb_bfs.py:200`, `ingestion/nrb/bfs_extract.py:94`.

These routines call `pg_terminate_backend` for any other session in the database whose state is `idle in transaction` and whose last SQL text mentions observations or staging. They do not check an owner/application identifier, a minimum idle duration, or whether that process is still alive.

Healthy psycopg sessions can be idle in a transaction between statements or while the application handles query results. The API's SELECT queries mention observations, so the predicate also matches healthy API work. A pipeline starting during a read or another load can disconnect that work and cause HTTP 500s or transaction rollbacks. The fiscal loader also performs storage uploads while a database transaction is open, widening its exposure. The election cleanup has an idle-age guard, but still lacks a reliable ownership/liveness check.

**Fix:** Remove query-text-based termination. Configure role-appropriate idle-transaction timeouts, close transactions before network work, use application names and a job lease, and clean up only verified abandoned work. Do not grant the serving identity session-termination privileges.

### 5. High remediation priority — Unsupported Next.js and dependency advisory matches

**Locations:** `web/package.json:14`, `web/package-lock.json:372`, `web/package-lock.json:306`, `web/package-lock.json:354`, `web/package-lock.json:460`, `.github/workflows/ci.yml:32`.

The committed lockfile resolves Next.js 14.2.35, ECharts 5.6.0, and PostCSS 8.4.31. The current npm audit flagged these plus nanoid. Next.js 14 is outside the supported release lines, and the declared `^14.2.15` range cannot move to a supported major. Current vendor guidance provides security releases on the 15.5 and 16.x lines. [Next.js support policy](https://nextjs.org/support-policy), [August security release](https://nextjs.org/blog/august-2026-security-release).

These are confirmed package/version matches, not a claim that every listed CVE is reachable in this application. For example, the Next.js RSC denial-of-service advisory lists 14.x but describes Server Function endpoints; no application-defined Server Actions were found. Rewrites, custom servers, and image remote-pattern configurations were also absent. The ECharts advisory concerns the distinct **Lines** series default tooltip; this code registers Line, Bar, and Map charts. Its custom-formatter issue is separately confirmed in finding 7. No untrusted CSS input or caller-controlled nanoid length was found. [Next.js RSC advisory](https://github.com/vercel/next.js/security/advisories/GHSA-h25m-26qc-wcjf), [Apache ECharts security guidance](https://echarts.apache.org/handbook/en/best-practices/security/).

The Python audit additionally matched development/install/migration tooling: pip, pytest, and sqlparse. Those packages are not in the minimal Vercel API requirements. Package-level matches should be triaged against the actual build and ingestion threat model.

**Fix:** Upgrade to a currently supported, fully patched Next.js release and refresh the lockfile; update the other flagged packages with compatibility checks. Add dependency auditing and automated update PRs to CI. Pin a reproducible Python resolution. The comments describing `~=0.115` and similar two-component Python requirements as preventing minor updates are incorrect: the installed FastAPI is 0.136.3 and is permitted by that range.

### 6. Medium — NRB promotion can erase a newly pending review

**Locations:** `scripts/nrb_bfs.py:237`, `scripts/nrb_bfs.py:253`, `scripts/nrb_bfs.py:332`, `ingestion/nrb/bfs_extract.py:121`.

Promotion reads approved staging rows into Python, commits, and later publishes those saved values. It finally updates staging status to promoted using IDs alone. Meanwhile, extraction can update the same row's value/raw reference and correctly set its status back to pending.

If extraction runs between the approved-row read and the final status update, promotion writes the old approved value but marks the new unreviewed staging version as promoted. The updated value is not itself published by this interleaving; its review queue entry is incorrectly removed. Two promoters can also select the same approved rows.

**Fix:** Claim and lock a specific staging version for promotion, or use compare-and-swap on version/hash plus `review_status='approved'`, checking affected row counts. Keep the protected selection, publication, and state transition in one transaction, or represent review versions immutably.

### 7. Medium — Stored/source-controlled text executes as HTML in chart tooltips

**Locations:** `web/components/TrendChart.tsx:39`, `web/components/ChoroplethMap.tsx:160`, `scripts/seed.py:203`, `scripts/seed.py:281`.

TrendChart interpolates indicator names and period labels into HTML strings without escaping. The map does the same for English and Nepali geography names. Indicator metadata can originate from external World Bank responses and is stored as text. React's normal text escaping does not apply to HTML generated by an ECharts formatter.

The actual TrendChart formatter was invoked with a synthetic indicator name containing an image error handler. Its output was passed to the installed ECharts renderer in an isolated browser with all network requests blocked. The handler executed and set a harmless marker. Exploitation requires control of a displayed upstream/database value; no public write endpoint or poisoned production record was demonstrated. ECharts explicitly identifies custom tooltip formatter output as raw HTML requiring caller escaping. [ECharts security guidelines](https://echarts.apache.org/handbook/en/best-practices/security/).

**Fix:** Escape every dynamic value before HTML interpolation, use DOM `textContent`, or use the safe rich-text rendering mode. Audit every custom formatter. A suitable CSP provides additional protection but does not replace correct escaping; upgrading ECharts alone does not fix custom formatter HTML.

### 8. Medium — Downloaded CSV can contain spreadsheet formulas

**Locations:** `web/lib/csv.ts:5`, `web/components/ElectionsPanel.tsx:312`, `web/components/PopulationDashboard.tsx:333`, `web/components/SeasonalityPanel.tsx:165`.

The CSV helper escapes commas, quotes, and line feeds, but leaves formula-leading text unchanged. Names from source data become CSV cells. The actual exporter preserved `=1+1` in a name column. If an attacker controls such text and a user opens the download in spreadsheet software, it can be interpreted as a formula; the impact of more capable formulas depends on that software's security settings. Ordinary CSV quoting does not neutralize formulas. [OWASP CSV injection](https://owasp.org/www-community/attacks/CSV_Injection).

**Fix:** Distinguish numeric values from text and neutralize formula-leading text using a policy tested in supported spreadsheet applications. Handle leading control characters and carriage returns as well as `=`, `+`, `-`, and `@`. Preserve actual negative numeric observations as numbers.

### 9. Medium — Database server identity verification is not enforced by code/config

**Locations:** `api/repository.py:257`, `.env.example:8`.

The API passes the DSN directly to psycopg, and the inspected DSN has no explicit `sslmode`. The observed connection did use TLS; this is not evidence of plaintext traffic. The repository does not require certificate/hostname verification, however. Libpq defaults to `prefer` unless overridden by external configuration, which does not authenticate the server. A network/DNS attacker could exploit a deployment relying on those defaults. External production SSL settings were not inspected. [PostgreSQL SSL modes](https://www.postgresql.org/docs/current/libpq-ssl.html).

**Fix:** Require `sslmode=verify-full` and the correct CA trust configuration for the Supabase pooler hostname. Validate these settings at startup and document them in the example environment.

### 10. Medium — Readers can observe incomplete ingestion releases

**Locations:** `ingestion/kalimati/price_history.py:473`, `ingestion/kalimati/price_history.py:483`, `ingestion/opendatanepal/kalimati_pipeline.py:361`, `api/repository.py:399`.

The Kalimati loaders commit individual batches. Every committed insert immediately becomes latest, while the ingestion log becomes successful only after all batches finish. The API does not restrict reads to completed releases. Users querying during a refresh can therefore see part of the new release mixed with previous data; if a later batch fails, earlier batches remain published. Queries used to assemble one response also use separate connections and snapshots.

This is a concurrent-read correctness limitation, independent of the duplicate-latest race. Resumability does not provide atomic publication.

**Fix:** Load into a staging/unpublished release, validate completion, and atomically publish it. Have API reads use the published version consistently. Retain resumable batch writes behind that publication boundary.

## Further hardening and operational issues

- **Connection pressure and slow failure:** `api/repository.py:257` opens a new connection for every repository method, with no application pool, explicit connect timeout, or bounded acquisition wait. A normal data request opens two sequential connections; seasonality opens three. Context managers do close connections, so this is churn/pressure rather than a connection leak. The configured database reports `max_connections=60`, a two-minute statement timeout, and no idle-transaction timeout. Sixty is a database backend limit shared with other users, not a user-count or pooler-client limit. Use a small bounded pool per instance or an appropriately configured external pooler, budget across instances, shorten API query deadlines, and return controlled 503/429 responses when capacity is exhausted.
- **Browser request amplification:** `web/components/FiscalPanel.tsx:151` starts nine independent series requests for one panel. The homepage mounts components that independently request data; there is no shared request cache. `web/lib/api.ts:74` has no timeout or AbortSignal, and component cleanup generally ignores late responses without aborting the request. Add shared caching, request deduplication, cancellation, and aggregate endpoints for frequently used page data.
- **Excess residual database grants:** The inspected `anon` and `authenticated` roles retain REFERENCES, TRIGGER, and TRUNCATE grants on public tables, despite lacking the ordinary DML grants in the inspected catalog. TRUNCATE is not governed by row-level policies. Revoke privileges these roles do not need and encode the intended grants/RLS configuration in migrations. No direct public RPC or HTTP route to exercise these residual privileges was established; do not describe this as proven anonymous deletion.
- **Local storage races and path confinement:** `ingestion/common/raw_lake.py:63` joins caller-provided paths without checking containment. Its local `put()` checks existence before `write_bytes()`, which is not an atomic create-if-absent. The backend is used by tests and is not exposed by the API. Use resolved-path containment and exclusive file creation before expanding its use.
- **Manifest lost updates:** `ingestion/nrb/bfs_acquire.py:55` and `ingestion/mof/acquire.py:327` read and rewrite whole JSON manifests without locking or atomic replacement. Concurrent runs can lose each other's entries or expose partially written JSON. Coordinate runs, atomically replace files, or store manifest identity in the database with a unique constraint. CI's NRB manifest changes are not persisted back to the repository by its workflow.
- **Unbounded upstream documents and remote link trust:** `ingestion/mof/acquire.py:281` buffers downloads in memory; its storage cap is checked only after downloading at line 440. The NRB downloader also buffers whole workbooks. MoF PDF destinations come from remote HTML and are fetched without an explicit destination allowlist/redirect validation. Compromised upstream content can therefore cause oversized downloads or unwanted requests from an ingestion worker. These are ingestion-side risks, not a user-controlled public API SSRF route. Limit streamed bytes, constrain destinations/redirects, and bound parser resources.
- **Security coverage in CI:** Current CI runs Python lint/types/tests and a frontend build, but no vulnerability scan, secret scan, PostgreSQL integration tests, concurrent-ingestion tests, or the standalone frontend test command. Add checks that enforce the specific invariants above. No CSP is configured in the checked Next.js config; inspect hosting headers before choosing a CSP compatible with the frontend.

## What simultaneous requests mean here

FastAPI's synchronous `def` handlers execute through a worker thread pool, so one database request does not force every other request to run sequentially. Repository instances are created per dependency call, and database cursors/connections are local to each method. This is a reasonable starting point for read concurrency. Starlette documents a shared default thread limiter; the installed environment reports 40 tokens. That setting is not a production throughput guarantee or a limit of 40 users. [Starlette thread pool](https://www.starlette.io/threadpool/).

The isolated probe added two 50 ms synthetic repository waits to every data request:

| Concurrent requests in batch | Whole batch duration | HTTP/result correctness |
| --- | --- | --- |
| 1 | 0.109 s | Passed |
| 10 | 0.137 s | Passed |
| 40 | 0.179 s | Passed |
| 80 | 0.308 s | Passed |

These values measure local ASGI routing, response handling, and synthetic waits only. They exclude actual SQL execution, pooler contention, network latency, cold starts, and host resource limits. The large-response measurement includes tracemalloc overhead. Neither test establishes a safe number of real users, and the Python-memory figure should not be multiplied into an exact production capacity prediction.

Before assigning a capacity number, load-test a staging deployment with representative data and the same database/pooler configuration. Use a realistic mix of catalog/search, one series slice, spark, geography, and seasonality requests. Increase concurrency gradually, measure p50/p95/p99 latency, error rate, queue/pool wait, active DB connections, query duration, and process memory. Include a simultaneous controlled refresh and verify one latest version per cell plus consistent publication. Define the acceptable latency/error budget before deciding the passing traffic level.

## Recommended implementation order

1. Separate the serving database identity, fix tooltip escaping, and upgrade supported dependencies.
2. Bound expensive API reads, remove the seasonality full-series fetch, and add caching, timeouts, connection budgeting, and overload handling.
3. Remove unsafe session termination; serialize ingestion publication, enforce latest-version uniqueness, and fix version-aware NRB promotion.
4. Add atomic release publication, safe CSV text export, explicit verified TLS, and reproducible permission/manifest handling.
5. Add PostgreSQL concurrency integration tests and run a representative staging load test to establish a defensible capacity target.

Existing strengths include parameterized public SQL filters (including breakdown keys), escaped LIKE wildcards, connection context managers, bounded search result counts, no public mutation routes, normal HTTPS certificate verification in source clients, enabled RLS in the inspected database, and no detected tracked credential patterns. Public unauthenticated GET access and wildcard CORS without credentials are consistent with this portal's public-data purpose and were not treated as vulnerabilities by themselves.
