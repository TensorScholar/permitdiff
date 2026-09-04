from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _release_workflow() -> str:
    return (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")


def test_github_release_stays_draft_until_pypi_succeeds() -> None:
    workflow = _release_workflow()

    draft_job = workflow.index("\n  github-release:\n")
    pypi_job = workflow.index("\n  publish-pypi:\n")
    publish_job = workflow.index("\n  github-release-publish:\n")

    assert draft_job < pypi_job < publish_job
    assert "release_args+=(--draft)" in workflow
    assert 'gh release create "$GITHUB_REF_NAME" dist/* "${release_args[@]}"' in workflow
    assert "needs: [build, github-release]" in workflow
    assert "needs: [github-release, publish-pypi]" in workflow
    assert 'gh release edit "$GITHUB_REF_NAME" --draft=false --verify-tag' in workflow
    assert workflow.index("release_args+=(--draft)") < pypi_job
    assert pypi_job < workflow.index('gh release edit "$GITHUB_REF_NAME" --draft=false')


def test_draft_creation_retry_never_deletes_release_tag() -> None:
    workflow = _release_workflow()

    assert 'gh release delete "$GITHUB_REF_NAME" --yes' in workflow
    assert "--cleanup-tag" not in workflow
    assert 'if [[ "$existing_state" != "true" ]]' in workflow
    assert "refusing to replace an already-published GitHub Release" in workflow


def test_pypi_publish_job_remains_oidc_only() -> None:
    workflow = _release_workflow()
    pypi_block = workflow.split("\n  publish-pypi:\n", maxsplit=1)[1].split(
        "\n  github-release-publish:\n", maxsplit=1
    )[0]

    assert "permissions:\n      id-token: write" in pypi_block
    assert "contents: write" not in pypi_block
    assert "packages-dir: pypi-dist/" in pypi_block
