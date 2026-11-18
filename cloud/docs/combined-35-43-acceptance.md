# PR35–43 combined review snapshot

Isolated integration branch only. Not main, not a deployment, and not a replacement for the existing PRs.

## Inputs

Base: 1dddf6e5dbca45b77a9e4e894010a463426b863d.

- PR35: 277e565930f666c467381643b95516c349791ae3
- PR36: 803945a64f1020b966cc8d6719234aafdad22686
- PR37: b540bfde70866f0350cdb5932f7393c54356bd93
- PR38: 71771ae365f46b0d59fe34daf53bcf2d5df9ba4e
- PR39: 1f408f01ecda2935cd2e3ac50167d04baebe112d
- PR40: b60491aceed75599479ab6656b205105b3cb2fa5
- PR41: 47044f24c330ab991f622bc016d53c739999bc9b
- PR42: ee9f016fe09ad1ad628d5ff69e3d203974dc8fba
- PR43: 66ab1bbbb9b7dbaa95125d626e719b363986ae7c

## Verification (2026-11-18 UTC)

- 76 offline tests passed: root unittest discovery 32; cloud boundary/build tests 39; installed model consumer tests 5.
- Simulated Docker COPY and fix_paths layout: the same 5 model consumer tests passed again. Not a Docker image build.
- Corrected executable bits for build_on_server.sh, build_sync.sh, deploy.sh verified; no release script executed.
- Dedicated test venv installed requests, BeautifulSoup and the existing local model wheel; pip check passed. This does not prove remote private-source installation or full production dependency installation.
- No live providers/database, collection, deployment or Mac operations.

## Run

From repository root: `python -m unittest discover -v -s tests`.

From cloud: `python -m unittest -v test_opening_hours_boundary test_entity_matching_boundary test_scoring_boundary test_postgrest_access test_search_result_parsers test_search_producer_startup test_text_normalization test_model_access_build test_model_access_release_entry`.

From cloud/vendor/pipeline: `python -m unittest -v test_model_access_migration` (requires the authorized model-access package).

## Remaining gates

PR40 targets PR35 and must be integrated there first. PR42 depends on PR37: integrate PR37, retarget PR42 to main, then rerun checks. Other PRs remain independently reviewable. Check remote heads again before any eventual merge. Real Docker/browser/full dependency builds, private-source authentication and production rollout are not proven or authorized by this snapshot.
