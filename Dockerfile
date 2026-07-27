# syntax=docker/dockerfile:1.7
FROM python:3.13-slim AS build
WORKDIR /build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
COPY pyproject.toml README.md LICENSE NOTICE MANIFEST.in ./
COPY src ./src
RUN python -m pip install --no-cache-dir build \
    && python -m build --wheel

FROM python:3.13-slim
LABEL org.opencontainers.image.title="PermitDiff" \
      org.opencontainers.image.description="Permission plans and CI gates for AI agents" \
      org.opencontainers.image.source="https://github.com/TensorScholar/permitdiff" \
      org.opencontainers.image.licenses="Apache-2.0"
RUN useradd --create-home --uid 10001 permitdiff
COPY --from=build /build/dist/*.whl /tmp/permitdiff.whl
RUN python -m pip install --no-cache-dir /tmp/permitdiff.whl \
    && rm /tmp/permitdiff.whl
USER permitdiff
WORKDIR /work
ENTRYPOINT ["permitdiff"]
CMD ["--help"]
