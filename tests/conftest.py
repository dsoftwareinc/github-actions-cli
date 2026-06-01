import pytest
from gha_cli.cli import GithubActionsTools

SAMPLE_WORKFLOW = """\
name: CI
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3.5.0
      - uses: actions/setup-python@v4.0.0
      - name: Run tests
        run: pytest
"""


@pytest.fixture(autouse=True)
def clear_class_caches():
    """Clear class-level caches between tests to prevent state pollution."""
    GithubActionsTools._wf_cache.clear()
    GithubActionsTools._GithubActionsTools__actions_latest_release.clear()
    yield
    GithubActionsTools._wf_cache.clear()
    GithubActionsTools._GithubActionsTools__actions_latest_release.clear()


@pytest.fixture
def local_repo(tmp_path):
    """Minimal local repo with one workflow file."""
    (tmp_path / ".git").mkdir()
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(SAMPLE_WORKFLOW)
    return tmp_path


@pytest.fixture
def tools(mocker):
    mocker.patch("gha_cli.cli.Github")
    from gha_cli.cli import GithubActionsTools
    from unittest.mock import MagicMock

    t = GithubActionsTools("fake-token")
    t.client = MagicMock()
    return t


@pytest.fixture
def tools_major_only(mocker):
    mocker.patch("gha_cli.cli.Github")
    from gha_cli.cli import GithubActionsTools
    from unittest.mock import MagicMock

    t = GithubActionsTools("fake-token", update_major_version_only=True)
    t.client = MagicMock()
    return t
