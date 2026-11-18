# PostgREST access boundary (internal refactor only)

The existing common_core headers/request/pagination mechanics now live in
postgrest_access.py. common_core still owns configuration precedence, project
paths, business constants, logging and notifications; its public headers/req/
fetch_all signatures remain compatible. Existing consumers such as
brand_chain_normalize.py, cleanup_findings.py and production_runner.py continue
through that facade. No business consumer or database policy is changed.

The extracted module reads no environment/config files and imports no project
module. Authentication, Requests transport and pacing are supplied by the
facade. No new package, private dependency or tool repository is introduced.
Existing Docker COPY *.py and build_sync cloud/*.py rules include the module.

Mature alternative reviewed: Supabase Python select/range/order APIs:
https://supabase.com/docs/reference/python/select
https://supabase.com/docs/reference/python/range
https://supabase.com/docs/reference/python/order
They are appropriate for a future SDK migration, but replacing this existing
raw-path/requests.Response API would change call and exception contracts.
This change therefore reuses Requests, rather than creating another HTTP stack
or pretending this adapter is an independent SDK.

Offline verification: from cloud, run python -m unittest -v test_postgrest_access
in an environment containing the existing requests dependency. Tests use only
synthetic requests/responses, no credentials or live databases. Six old/new
request scenarios were also compared for exact calls, return status, exception
text and sleep traces. No container build, live query or deployment occurred.

Inherited behavior is intentionally not silently repaired: short pages end
pagination (server-side caps must match the caller's page size); offsets are
not a snapshot under concurrent writes; custom timeout currently applies only
to the first retry attempt; existing write-retry behavior is unchanged.
Those require separately scoped behavior changes, not a new abstraction here.
