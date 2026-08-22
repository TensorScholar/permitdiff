# syntax=docker/dockerfile:1.7
# The python:3.13-slim base is pinned to its immutable, multi-architecture OCI
# index digest (Python 3.13.14 slim-trixie). Pinning the tag instead of the
# digest would break reproducibility, because the tag moves on every upstream
# release. To refresh intentionally, update every FROM line to a newly verified
# digest and re-run scripts/refresh_docker_lock.py: see
# docs/docker-reproducibility.md.
#
# Supported platforms: linux/amd64 and linux/arm64 (both validated end to end).
# The OCI index contains other architectures; they are NOT claimed as supported
# until their artifact hashes are validated and merged into the locks.
FROM python:3.13-slim@sha256:9662417aace5ae7b8e2609cce472b72a8958e134ba372808abe9cc1a0c0125e6 AS resolve
WORKDIR /resolve
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
# The resolve stage only materializes the authoritative runtime dependency
# declarations from pyproject.toml; it installs nothing. The single
# authoritative dependency resolution per platform happens in
# scripts/refresh_docker_lock.py via `pip download --only-binary=:all:`, and
# exactly the artifacts it resolves are hashed into docker/requirements.lock.
# The deterministic final image never uses this stage: it installs only the
# committed hashed lock.
COPY pyproject.toml scripts/emit_project_dependencies.py ./
RUN python emit_project_dependencies.py > deps.txt

FROM python:3.13-slim@sha256:9662417aace5ae7b8e2609cce472b72a8958e134ba372808abe9cc1a0c0125e6 AS build
WORKDIR /build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
COPY pyproject.toml README.md LICENSE NOTICE MANIFEST.in ./
COPY src ./src
COPY docker/build-requirements.lock ./docker/build-requirements.lock
# Build toolchain (build, packaging, pyproject_hooks, setuptools) is installed
# from docker/build-requirements.lock with --require-hashes and --only-binary.
# The wheel is then built with --no-isolation so that the already-installed,
# hash-verified toolchain is used and pip's implicit isolated build environment
# cannot bypass the lock by re-resolving build-system requires from the network.
RUN python -m pip install --no-cache-dir \
      --only-binary=:all: \
      --require-hashes \
      -r docker/build-requirements.lock \
    && python -m build --wheel --no-isolation

FROM python:3.13-slim@sha256:9662417aace5ae7b8e2609cce472b72a8958e134ba372808abe9cc1a0c0125e6
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
LABEL org.opencontainers.image.title="PermitDiff" \
      org.opencontainers.image.description="Permission plans and CI gates for AI agents" \
      org.opencontainers.image.source="https://github.com/TensorScholar/permitdiff" \
      org.opencontainers.image.licenses="Apache-2.0"
RUN useradd --create-home --uid 10001 permitdiff
# Copy the wheel verbatim. Renaming it (for example to /tmp/permitdiff.whl)
# produces an invalid PEP 427 filename and pip refuses to install it.
COPY --from=build /build/dist/*.whl /tmp/dist/
# Runtime dependencies are locked to exact versions in docker/requirements.lock.
# --require-hashes makes every remotely fetched artifact verify against the
# committed SHA-256 set, and --only-binary=:all: forbids sdist fallback, so the
# deterministic final build cannot silently fetch an undeclared or unhashed
# artifact: any missing or unauthorized distribution fails the build loudly.
COPY docker/requirements.lock /tmp/docker/requirements.lock
RUN python -m pip install --no-cache-dir \
      --only-binary=:all: \
      --require-hashes \
      -r /tmp/docker/requirements.lock \
    && python -m pip install --no-cache-dir --no-deps /tmp/dist/*.whl \
    && python -m pip check \
    && rm -rf /tmp/dist /tmp/docker
USER permitdiff
WORKDIR /work
ENTRYPOINT ["permitdiff"]
CMD ["--help"]