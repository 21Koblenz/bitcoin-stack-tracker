from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
BUILD_WORKFLOW = (ROOT / ".github/workflows/publish-tor-gateway.yaml").read_text(encoding="utf-8")
ASSET_WORKFLOW = (ROOT / ".github/workflows/release-assets.yaml").read_text(encoding="utf-8")


def test_home_assistant_install_buttons_are_kept_in_readme():
    assert "badges/hacs_repository.svg" in README
    assert "owner=21Koblenz&repository=bitcoin-stack-tracker&category=integration" in README
    assert "badges/supervisor_add_addon_repository.svg" in README
    assert "repository_url=https%3A%2F%2Fgithub.com%2F21Koblenz%2Fbitcoin-stack-tracker" in README
    assert "badges/config_flow_start.svg" in README
    assert "domain=bitcoin_stack_tracker" in README


def test_ghcr_publish_jobs_keep_package_write_permission():
    assert BUILD_WORKFLOW.count("packages: write") >= 2
    assert "org.opencontainers.image.source=https://github.com/${{ github.repository }}" in BUILD_WORKFLOW


def test_release_uploads_zip_and_sha256():
    assert "release:" in ASSET_WORKFLOW
    assert "types:" in ASSET_WORKFLOW and "published" in ASSET_WORKFLOW
    assert "contents: write" in ASSET_WORKFLOW
    assert "git archive --format=zip" in ASSET_WORKFLOW
    assert "sha256sum" in ASSET_WORKFLOW
    assert "gh release upload" in ASSET_WORKFLOW


def test_integration_only_release_tag_does_not_force_gateway_version_bump():
    assert 'if [[ "${GITHUB_REF_NAME}" == "v${version}" ]]; then' in BUILD_WORKFLOW
    assert "kein Gateway-Publish." in BUILD_WORKFLOW
    assert "push: ${{ needs.prepare.outputs.publish }}" in BUILD_WORKFLOW
    assert "if: needs.prepare.outputs.publish == 'true'" in BUILD_WORKFLOW
