# Isolated model access migration

Task branch only; no production deployment or main merge.

Real consumer: cloud/vendor/pipeline/fleet_grid_run.py, call_one. Model request execution now uses the independently owned private agent-model-access package at commit 0d9dd8d7ad5f65f85a2d057b58accb9f5122e38a. No private package source is copied here. Dependency reference contains no credentials; authorized SSH access is required. Alternatively build the same commit's wheel in an authorized checkout and install offline.

Install into an isolated Python 3.12 environment using requirements-model-access.txt plus the existing requests dependency. Run from cloud/vendor/pipeline: python -m unittest -v test_model_access_migration. No model credentials or database access required by the tests.

Five isolated tests passed before this task branch: request/response parity, authorization filtering, existing parser behavior, HTTP401 contract, connection error fields. Tests use mocked network transport, not a live provider. Other original functions remain unchanged. Business prompt stays here; provider discovery, web-search parameter mapping and source parsing still use the original model_providers module. This is one real consumer call-boundary migration, not full removal of legacy dependencies.

Private dependency installation in production, public CI authentication, real provider behavior and proxy support are not verified. Do not merge/deploy until deployment can obtain the pinned private package without embedding secrets. Default cloud SOCKS proxy may require the optional socks dependency; no global proxy changes made.
