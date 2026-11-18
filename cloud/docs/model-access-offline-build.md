# Model access dependency in the existing Docker build

This build installs the private package without copying its source or credentials into this public repository. It requires Docker BuildKit/buildx with named build contexts.

On an already-authorized build host (or via an authorized fixed-commit connector export), check out private agent-model-access commit `0d9dd8d7ad5f65f85a2d057b58accb9f5122e38a`. Using Python 3.12, build its wheel and collect its runtime dependency wheels into a private wheelhouse, outside the public checkout. Use the same Linux architecture as the image for binary dependency wheels. Record the main wheel's SHA256 alongside the checked-out commit in the private build record. Do not add credentials, wheels, or private source to the public repository.

Pass that private wheelhouse as a separate build context, not as a directory within cloud:

```sh
docker buildx build --load \
  --build-context model_wheels=/absolute/private/wheelhouse \
  --build-arg MODEL_ACCESS_WHEEL_SHA256=<recorded-64-character-wheel-sha256> \
  -t food-model-access-check ./cloud
```

The Docker installation entry validates the required wheel hash, installs only from the supplied wheelhouse, and checks the public import. Missing wheels, dependencies, or a wrong hash fail the build. The hash verifies the selected artifact; source provenance still depends on the authorized build host's commit/build record. No SSH agent, token, new credential, or private network access is required inside Docker. Runtime credentials remain supplied through the project's existing mechanism.

Run `python -m unittest -v test_model_access_build` from cloud to check this exact installation script in fresh virtual environments with synthetic wheels. Those tests contain no private package source and prove installation wiring only. They do not prove a full Docker build, actual provider connectivity, or production rollout. Run the existing five model-access migration tests against the real package in the candidate image before deployment; supply no model credentials and do not run the production entrypoint.

The public requirements-model-access.txt SSH reference remains a developer option for already-authorized environments. The Docker path intentionally does not use it. Existing build/release invocations must supply the named wheel context and hash; without them the build fails rather than shipping a missing dependency.

## Existing release path

`deploy.sh` first loads `food-cloud-image.tgz`, otherwise reuses `food-cloud:local`, and only builds if neither exists. Those first two paths are unchanged. Its build fallback now calls `build_model_image.sh` with the same image tag. The wrapper requires the private wheelhouse and recorded hash, validates them before Docker, and fixes the existing amd64 target. It does not deploy. Missing build inputs stop the fallback before starting a service; there is no silent legacy-model fallback.

For an isolated build only:

```sh
MODEL_WHEELHOUSE=/absolute/private/wheelhouse \
MODEL_ACCESS_WHEEL_SHA256=<recorded-sha256> \
bash cloud/build_model_image.sh
```

The default tag is `food-model-access-check`, not production. Do not run `deploy.sh` for validation: it starts cron/collection. Do not reuse an old production image as proof of this branch. A release must explicitly rebuild and validate the candidate, then use the project's existing image transfer/tag procedure. The final image necessarily contains the installed private package: keep image files and registry destinations private; do not publish them or upload wheelhouses to the public repository.

No Docker binary/daemon is available in the verification workspace. Shell checks and fresh-venv installation tests are not image-build proof. BuildKit availability, mirror access, browser installation and candidate-image consumer tests remain required before merge/release.
