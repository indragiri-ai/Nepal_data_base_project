# reference/mof — provenance

## geotrust_tls_rsa_ca_g1.pem

**What:** the "GeoTrust TLS RSA CA G1" intermediate certificate (issued by
DigiCert), needed to complete the TLS chain when connecting to `mof.gov.np`.

**Why it's here:** `mof.gov.np`'s webserver is misconfigured — it serves only
its own leaf certificate during the TLS handshake and omits this intermediate
(verified 2026-09-03 with `openssl s_client -connect mof.gov.np:443
-showcerts`, which returns exactly one certificate in the chain). Browsers
and curl on Windows tolerate this because they cache or fetch the missing
intermediate independently (AIA chasing / OS trust store); Python's
`requests`+`certifi` does strict validation from only what the server
presents and fails with `CERTIFICATE_VERIFY_FAILED`. Disabling verification
(`verify=False`) was rejected as a security downgrade — this project's rule
is to fix the root cause, not bypass it. `ingestion/mof/acquire.py` merges
this file with `certifi`'s bundle at request time so the chain resolves
correctly without weakening verification for any other host.

**Source:** fetched directly from DigiCert's own certificate repository,
`https://cacerts.digicert.com/GeoTrustTLSRSACAG1.crt` (2026-09-03), not from
`mof.gov.np` itself — the whole point is that the government server cannot be
trusted to supply this file. Subject/issuer confirmed to match exactly what
`mof.gov.np`'s leaf certificate names as its issuer, and the completed chain
(leaf + this intermediate + certifi's root bundle) verifies OK with
`openssl verify`.

**Fingerprint (SHA-256):**
`9f382a3bdf9e561373513eb172998848c3b0ff561ed4274ef98ac8b609c8bd53`

**If this ever needs updating:** DigiCert rotates intermediates on a multi-
year cycle; if `mof.gov.np`'s leaf certificate someday names a different
issuer, re-fetch from `cacerts.digicert.com` (or whichever CA now issues it)
and update this file + the fingerprint above — never guess or copy one from
an untrusted source.
