"""Integration tests for CLI commands using Click's CliRunner."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from gha_cli.cli import GithubActionsTools, cli
from tests.conftest import SAMPLE_WORKFLOW


@pytest.fixture
def runner():
    return CliRunner()


def _make_mock_release(tag="v4.0.0"):
    r = MagicMock()
    r.tag_name = tag
    r.last_modified_datetime = datetime.now(timezone.utc)
    return r


def _setup_remote_mock(mock_github_cls, workflow_content=SAMPLE_WORKFLOW):
    mock_content = MagicMock()
    mock_content.decoded_content = workflow_content.encode()
    mock_content.sha = "abc123"
    mock_workflow = MagicMock()
    mock_workflow.path = ".github/workflows/ci.yml"
    mock_repo = MagicMock()
    mock_repo.get_workflows.return_value = [mock_workflow]
    mock_repo.get_contents.return_value = mock_content
    mock_github_cls.return_value.get_repo.return_value = mock_repo
    return mock_repo


class TestListWorkflows:
    def test_local_repo_lists_ci_yml(self, runner, local_repo):
        result = runner.invoke(cli, ["--repo", str(local_repo), "--github-token", "fake", "list-workflows"])
        assert result.exit_code == 0
        assert "ci.yml" in result.output

    def test_local_repo_shows_workflow_name(self, runner, local_repo):
        result = runner.invoke(cli, ["--repo", str(local_repo), "--github-token", "fake", "list-workflows"])
        assert "CI" in result.output

    def test_remote_repo_lists_workflow_path(self, runner, mocker):
        mock_github = mocker.patch("gha_cli.cli.Github")
        _setup_remote_mock(mock_github)
        result = runner.invoke(cli, ["--repo", "owner/repo", "--github-token", "fake", "list-workflows"])
        assert result.exit_code == 0
        assert ".github/workflows/ci.yml" in result.output
        assert "CI" in result.output


class TestListActions:
    def test_lists_uses_steps_from_workflow(self, runner, local_repo):
        path = str(local_repo / ".github" / "workflows" / "ci.yml")
        result = runner.invoke(
            cli,
            ["--repo", str(local_repo), "--github-token", "fake", "list-actions", path],
        )
        assert result.exit_code == 0
        assert "actions/checkout@v3.5.0" in result.output
        assert "actions/setup-python@v4.0.0" in result.output

    def test_does_not_list_run_steps(self, runner, local_repo):
        path = str(local_repo / ".github" / "workflows" / "ci.yml")
        result = runner.invoke(
            cli,
            ["--repo", str(local_repo), "--github-token", "fake", "list-actions", path],
        )
        assert "pytest" not in result.output


class TestUpdateActionsCommand:
    def test_dry_run_shows_available_update(self, runner, local_repo, mocker):
        mock_github = mocker.patch("gha_cli.cli.Github")
        mock_github.return_value.get_repo.return_value.get_latest_release.return_value = _make_mock_release("v4.0.0")

        result = runner.invoke(
            cli,
            ["--repo", str(local_repo), "--github-token", "fake", "update-actions"],
        )
        assert result.exit_code == 0
        assert "==>" in result.output
        assert "v4.0.0" in result.output

    def test_dry_run_does_not_modify_file(self, runner, local_repo, mocker):
        mock_github = mocker.patch("gha_cli.cli.Github")
        mock_github.return_value.get_repo.return_value.get_latest_release.return_value = _make_mock_release("v4.0.0")
        original = (local_repo / ".github" / "workflows" / "ci.yml").read_text()

        runner.invoke(cli, ["--repo", str(local_repo), "--github-token", "fake", "update-actions"])

        assert (local_repo / ".github" / "workflows" / "ci.yml").read_text() == original

    def test_update_flag_writes_new_version_to_file(self, runner, local_repo, mocker):
        mock_github = mocker.patch("gha_cli.cli.Github")
        mock_github.return_value.get_repo.return_value.get_latest_release.return_value = _make_mock_release("v4.0.0")

        result = runner.invoke(
            cli,
            ["--repo", str(local_repo), "--github-token", "fake", "update-actions", "--update"],
        )

        assert result.exit_code == 0
        content = (local_repo / ".github" / "workflows" / "ci.yml").read_text()
        assert "actions/checkout@v4.0.0" in content

    def test_no_update_needed_when_already_at_latest(self, runner, local_repo, mocker):
        mock_github = mocker.patch("gha_cli.cli.Github")
        # Return same versions as in the workflow — no upgrade available
        mock_github.return_value.get_repo.return_value.get_latest_release.return_value = _make_mock_release("v3.5.0")

        result = runner.invoke(
            cli,
            ["--repo", str(local_repo), "--github-token", "fake", "update-actions"],
        )
        assert result.exit_code == 0
        assert "==>" not in result.output

    def test_major_only_flag_shows_only_major_in_update(self, runner, local_repo, mocker):
        mock_github = mocker.patch("gha_cli.cli.Github")
        mock_github.return_value.get_repo.return_value.get_latest_release.return_value = _make_mock_release("v4.1.2")

        result = runner.invoke(
            cli,
            ["--repo", str(local_repo), "--github-token", "fake", "--major-only", "update-actions", "--update"],
        )
        assert result.exit_code == 0
        content = (local_repo / ".github" / "workflows" / "ci.yml").read_text()
        assert "actions/checkout@v4" in content

    def test_missing_token_prints_warning(self, runner, local_repo):
        result = runner.invoke(cli, ["--repo", str(local_repo), "update-actions"])
        assert "GitHub connection token not provided" in result.output

    def test_default_subcommand_runs_update_actions(self, runner, local_repo, mocker):
        mocker.patch("gha_cli.cli.Github")
        # Invoking cli without a subcommand should implicitly run update_actions
        result = runner.invoke(cli, ["--repo", str(local_repo), "--github-token", "fake"])
        assert result.exit_code == 0
        assert "ci.yml" in result.output

    def test_remote_repo_commits_updated_workflow(self, runner, mocker):
        mock_github = mocker.patch("gha_cli.cli.Github")
        mock_repo = _setup_remote_mock(mock_github)
        mock_repo.get_latest_release.return_value = _make_mock_release("v4.0.0")

        result = runner.invoke(
            cli,
            ["--repo", "owner/repo", "--github-token", "fake", "update-actions", "--update"],
        )
        assert result.exit_code == 0
        mock_repo.update_file.assert_called()
