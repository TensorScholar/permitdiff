# Docker dependency pinning and supply-chain integrity (B1-F08)

The Docker image is built to be reproducible and hash-checked: the same commit
produces the same installed dependency set on the supported platforms, and
every remotely fetched artifact is verified against committed SHA-256 hashes.
There is intentionally no `docker push` workflow; the image is built by whoever
runs the Dockerfile.

## Supported platforms

The image is validated and supported on exactly:

* `linux/amd64`
* `linux/arm64`

Both platforms are validated end to end with `docker build --no-cache`,
`permitdiff --help` / `--version`, `pip check`, and hash-checking verification
of every downloaded artifact.

The pinned base image is a multi-architecture OCI index that also lists
architectures such as `linux/386`, `linux/arm/v5`, `linux/arm/v7`,
`linux/ppc64le`, `linux/riscv64`, and `linux/s390x`. Those architectures are
**not** claimed as supported: the runtime lock only authorizes the artifact
hashes collected for the supported platforms. Adding a platform is an
intentional change — add it to `SUPPORTED_PLATFORMS` in
`scripts/refresh_docker_lock.py`, validate the build end to end, and re-run the
refresh so the platform's artifact hashes are merged into the lock.

## What is pinned and how it is verified

1. **Base image by immutable digest.** All three stages (resolve, build,
   runtime) use
   `python:3.13-slim@sha256:9662417aace5ae7b8e2609cce472b72a8958e134ba372808abe9cc1a0c0125e6`
   (Python 3.13.14 slim-trixie). The digest pins the multi-architecture OCI
   index, so every supported platform builds from the same immutable
   reference.
2. **Runtime dependencies (`docker/requirements.lock`).** One lock, with exact
   version pins and SHA-256 hashes for both supported platforms. The runtime
   stage installs it with `--require-hashes` and `--only-binary=:all:`:

   * `--require-hashes` puts pip into hash-checking mode: any artifact that
     does not match a committed hash — a tampered upload, a different binary
     build, or a version that is not in the lock — fails the Docker build
     loudly. An undeclared or unhashed dependency cannot be fetched silently.
   * `--only-binary=:all:` forbids source-distribution fallback, so the build
     never compiles an unverified sdist.
   * Binary wheels such as `pydantic-core` and `PyYAML` differ per platform,
     so they carry **two `--hash` entries** — one per supported platform.
     pip accepts multiple hashes per requirement specifically to authorize the
     alternative binary artifacts of one committed lock; a per-platform
     hashed lock is therefore not required.
   * `pip check` at the end of the runtime stage fails the build if the
     installed wheel's own dependency requirements are not satisfied by the
     locked set, so a dependency that is missing from the lock is caught even
     by the `--no-deps` wheel install.
3. **Build toolchain (`docker/build-requirements.lock`).** The build frontend
   and its dependencies — `build==1.5.0`, `packaging==26.3`,
   `pyproject_hooks==1.2.0`, `setuptools==84.0.0` (the versions observed
   against the pinned base image) — are installed in the build stage with the
   same `--require-hashes` / `--only-binary=:all:` rules. The wheel is then
   built with `python -m build --wheel --no-isolation`, so pip's implicit
   isolated build environment cannot bypass the lock by re-resolving the
   `setuptools>=77` build-system requirement from the network. The public
   build-system constraint in `pyproject.toml` intentionally keeps the
   upstream range; only the Docker build is exact-pinned.

## How to refresh (generative, not circular)

The refresh intentionally does **not** read the committed locks, and there is
exactly **one** authoritative dependency resolution per supported platform. The
Docker `resolve` stage only materializes the runtime dependency declarations
from `pyproject.toml` (`[project].dependencies`) into `deps.txt`; it installs
nothing. `scripts/refresh_docker_lock.py` then:

1. builds the resolve stage for every supported platform (`--no-cache`,
   `--platform linux/amd64` and `linux/arm64`);
2. performs the single authoritative resolution per platform: one
   `pip download --only-binary=:all:` run against `deps.txt` in each
   platform's container, capturing exactly the wheel artifacts that platform's
   resolution would install;
3. computes the SHA-256 of every artifact;
4. validates that the platforms resolved **structurally identical graphs** —
   the same canonical distribution names and the same versions on every
   platform, differing only in artifact hashes — and aborts with a diagnostic
   naming the platform and the missing packages otherwise. This is required
   because the committed lock format is unconditional (no platform markers):
   silently merging graphs that differ in names or versions would
   misrepresent the platform dependency sets;
5. regenerates `docker/requirements.lock` and
   `docker/build-requirements.lock` (the latter from the approved tool
   versions in `BUILD_TOOL_PINS` of the script) and writes them atomically.

The generator itself is intentionally networked and unhashed during an
explicit refresh — its purpose is to discover candidate artifacts and record
their hashes. The production image never uses that path: the deterministic
final runtime stage installs only the committed hashed lock with
`--require-hashes`.

Refresh procedure, in order:

1. Verify a new `python:3.13-slim` digest and replace the digest in every
   `FROM` line of the Dockerfile. All stages must reference the same digest.
2. If the build toolchain changes intentionally, update `BUILD_TOOL_PINS` in
   `scripts/refresh_docker_lock.py` (and `tests/test_docker_contract.py` if a
   digest constant changed).
3. Regenerate both locks:

   ```sh
   python scripts/refresh_docker_lock.py
   ```

4. Commit the regenerated locks and re-run the validation below.

## Validation

```sh
docker build --no-cache --platform linux/arm64 -t permitdiff:arm64 .                                  # linux/arm64
docker build --no-cache --platform linux/amd64 -t permitdiff:amd64 .            # linux/amd64
docker run --rm <image> --help
docker run --rm <image> --version
docker run --rm --entrypoint /usr/local/bin/python <image> -m pip freeze
docker run --rm --entrypoint /usr/local/bin/python <image> -m pip check
```

Hash checking is enforced by pip during the build; a tampered lock fails with
`THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE`, and a
missing distribution fails the resolution. To verify the fail-loud behavior
locally, delete one `--hash` entry (or one pin) from
`docker/requirements.lock` and rebuild — the build must fail — then restore the
file.