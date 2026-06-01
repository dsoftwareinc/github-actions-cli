"""Tests for GithubActionsTools and helper functions."""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest
from github import UnknownObjectException

from gha_cli.cli import GithubActionsTools, _is_sha, ActionVersion
from tests.conftest import SAMPLE_WORKFLOW


def _unknown_object_exception():
    return UnknownObjectException(404, {"message": "Not Found"}, None)


class TestIsSha:
    def test_valid_lowercase_sha(self):
        assert _is_sha("a" * 40) is True

    def test_valid_hex_digits(self):
        assert _is_sha("0123456789abcdef" * 2 + "01234567") is True

    def test_uppercase_treated_as_valid(self):
        assert _is_sha("ABCDEF1234567890" * 2 + "ABCDEF12") is True

    def test_semver_tag_is_not_sha(self):
        assert _is_sha("v1.2.3") is False

    def test_short_sha_is_not_sha(self):
        assert _is_sha("deadbeef") is False

    def test_39_chars_is_not_sha(self):
        assert _is_sha("a" * 39) is False

    def test_41_chars_is_not_sha(self):
        assert _is_sha("a" * 41) is False

    def test_non_hex_chars_invalid(self):
        assert _is_sha("z" * 40) is False


class TestCompareVersions:
    def test_patch_bump_newer(self, tools):
        assert tools._compare_versions("v1.2.4", "v1.2.3") == 1

    def test_patch_bump_older(self, tools):
        assert tools._compare_versions("v1.2.3", "v1.2.4") == -1

    def test_equal_versions(self, tools):
        assert tools._compare_versions("v1.2.3", "v1.2.3") == 0

    def test_major_bump_newer(self, tools):
        assert tools._compare_versions("v2.0.0", "v1.9.9") == 1

    def test_minor_bump_newer(self, tools):
        assert tools._compare_versions("v1.3.0", "v1.2.9") == 1

    def test_no_v_prefix(self, tools):
        assert tools._compare_versions("1.2.4", "1.2.3") == 1

    def test_missing_patch_segment_counts_as_zero(self, tools):
        assert tools._compare_versions("1.2", "1.2.1") == -1
        assert tools._compare_versions("1.2.1", "1.2") == 1

    def test_major_only_same_major_is_equal(self, tools_major_only):
        assert tools_major_only._compare_versions("v1.9.9", "v1.0.0") == 0

    def test_major_only_higher_major_is_newer(self, tools_major_only):
        assert tools_major_only._compare_versions("v2.0.0", "v1.9.9") == 1


class TestFixVersion:
    def test_full_version_unchanged(self, tools):
        assert tools._fix_version("v1.2.3") == "v1.2.3"

    def test_major_only_strips_minor_and_patch(self, tools_major_only):
        assert tools_major_only._fix_version("v1.2.3") == "v1"

    def test_major_only_already_just_major(self, tools_major_only):
        assert tools_major_only._fix_version("v4") == "v4"


class TestIsLocalRepo:
    def test_detects_local_repo(self, tmp_path):
        (tmp_path / ".git").mkdir()
        assert GithubActionsTools.is_local_repo(str(tmp_path)) is True

    def test_dir_without_git_is_not_local_repo(self, tmp_path):
        assert GithubActionsTools.is_local_repo(str(tmp_path)) is False

    def test_nonexistent_path_is_not_local_repo(self):
        assert GithubActionsTools.is_local_repo("/nonexistent/path/xyz") is False


class TestListFullPaths:
    def test_returns_yml_and_yaml_files(self, tmp_path):
        (tmp_path / "a.yml").write_text("")
        (tmp_path / "b.yaml").write_text("")
        (tmp_path / "c.txt").write_text("")
        paths = GithubActionsTools.list_full_paths(str(tmp_path))
        names = {p.rsplit("/", 1)[-1] for p in paths}
        assert names == {"a.yml", "b.yaml"}

    def test_nonexistent_path_returns_empty_set(self):
        assert GithubActionsTools.list_full_paths("/nonexistent/dir") == set()


class TestGetActionLatestRelease:
    def _mock_release(self, tag="v3.0.0", age_days=0):
        r = MagicMock()
        r.tag_name = tag
        r.last_modified_datetime = datetime.now(timezone.utc) - timedelta(days=age_days)
        return r

    def test_no_at_sign_returns_none(self, tools):
        assert tools.get_action_latest_release("actions/checkout") is None

    def test_newer_semver_returns_latest_tag(self, tools):
        tools.client.get_repo.return_value.get_latest_release.return_value = self._mock_release("v3.0.0")
        result = tools.get_action_latest_release("actions/checkout@v2.0.0")
        assert result == "v3.0.0"

    def test_same_version_returns_none(self, tools):
        tools.client.get_repo.return_value.get_latest_release.return_value = self._mock_release("v2.0.0")
        result = tools.get_action_latest_release("actions/checkout@v2.0.0")
        assert result is None

    def test_older_release_than_current_returns_none(self, tools):
        tools.client.get_repo.return_value.get_latest_release.return_value = self._mock_release("v1.0.0")
        result = tools.get_action_latest_release("actions/checkout@v2.0.0")
        assert result is None

    def test_repo_not_found_returns_none(self, tools):
        tools.client.get_repo.side_effect = _unknown_object_exception()
        result = tools.get_action_latest_release("nonexistent/action@v1.0.0")
        assert result is None

    def test_no_releases_returns_none(self, tools):
        tools.client.get_repo.return_value.get_latest_release.side_effect = _unknown_object_exception()
        result = tools.get_action_latest_release("actions/checkout@v1.0.0")
        assert result is None

    def test_sha_version_with_newer_release_returns_tag(self, tools):
        sha = "a" * 40
        release_time = datetime.now(timezone.utc)

        mock_release = self._mock_release("v3.0.0")
        mock_release.last_modified_datetime = release_time

        mock_commit = MagicMock()
        mock_commit.last_modified_datetime = release_time - timedelta(days=7)

        mock_repo = MagicMock()
        mock_repo.get_latest_release.return_value = mock_release
        mock_repo.get_commit.return_value = mock_commit
        tools.client.get_repo.return_value = mock_repo

        result = tools.get_action_latest_release(f"actions/checkout@{sha}")
        assert result == "v3.0.0"

    def test_sha_version_with_older_release_returns_none(self, tools):
        sha = "b" * 40
        now = datetime.now(timezone.utc)

        mock_release = self._mock_release("v1.0.0")
        mock_release.last_modified_datetime = now - timedelta(days=7)

        mock_commit = MagicMock()
        mock_commit.last_modified_datetime = now  # commit is newer than release

        mock_repo = MagicMock()
        mock_repo.get_latest_release.return_value = mock_release
        mock_repo.get_commit.return_value = mock_commit
        tools.client.get_repo.return_value = mock_repo

        result = tools.get_action_latest_release(f"actions/checkout@{sha}")
        assert result is None

    def test_cache_hit_returns_latest_without_api_call(self, tools):
        GithubActionsTools._GithubActionsTools__actions_latest_release["actions/checkout"] = (
            "v3.0.0",
            datetime.now(timezone.utc),
        )
        result = tools.get_action_latest_release("actions/checkout@v2.0.0")
        assert result == "v3.0.0"
        tools.client.get_repo.assert_not_called()

    def test_cache_hit_same_version_returns_none(self, tools):
        GithubActionsTools._GithubActionsTools__actions_latest_release["actions/checkout"] = (
            "v2.0.0",
            datetime.now(timezone.utc),
        )
        result = tools.get_action_latest_release("actions/checkout@v2.0.0")
        assert result is None
        tools.client.get_repo.assert_not_called()

    def test_result_is_cached_after_first_call(self, tools):
        tools.client.get_repo.return_value.get_latest_release.return_value = self._mock_release("v3.0.0")
        tools.get_action_latest_release("actions/checkout@v2.0.0")
        tools.get_action_latest_release("actions/checkout@v2.0.0")
        # get_repo called only once; second call used the cache
        tools.client.get_repo.assert_called_once()

    def test_action_with_sub_path_queries_owner_repo(self, tools):
        """actions/upload-artifact/merge@v3 should query the actions/upload-artifact repo."""
        tools.client.get_repo.return_value.get_latest_release.return_value = self._mock_release("v4.0.0")
        result = tools.get_action_latest_release("actions/upload-artifact/merge@v3.0.0")
        assert result == "v4.0.0"
        tools.client.get_repo.assert_called_once_with("actions/upload-artifact")

    def test_action_with_sub_path_cache_uses_full_name(self, tools):
        """Cache key is the full action name, not the truncated owner/repo."""
        tools.client.get_repo.return_value.get_latest_release.return_value = self._mock_release("v4.0.0")
        tools.get_action_latest_release("actions/upload-artifact/merge@v3.0.0")
        assert "actions/upload-artifact/merge" in GithubActionsTools._GithubActionsTools__actions_latest_release

    def test_major_only_returns_major_tag(self, tools_major_only):
        tools_major_only.client.get_repo.return_value.get_latest_release.return_value = MagicMock(
            tag_name="v4.1.0",
            last_modified_datetime=datetime.now(timezone.utc),
        )
        result = tools_major_only.get_action_latest_release("actions/checkout@v3.0.0")
        assert result == "v4.1.0"


class TestGetWorkflowActionNames:
    def test_parses_uses_steps_from_local_workflow(self, tools, local_repo):
        path = str(local_repo / ".github" / "workflows" / "ci.yml")
        actions = tools.get_workflow_action_names(str(local_repo), path)
        assert "actions/checkout@v3.5.0" in actions
        assert "actions/setup-python@v4.0.0" in actions

    def test_step_without_uses_not_included(self, tools, local_repo):
        path = str(local_repo / ".github" / "workflows" / "ci.yml")
        actions = tools.get_workflow_action_names(str(local_repo), path)
        assert len(actions) == 2  # only the two uses: steps

    def test_parses_remote_workflow(self, tools):
        yaml_content = (
            "name: CI\njobs:\n  build:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - uses: actions/checkout@v4\n"
        )
        mock_content = MagicMock()
        mock_content.decoded_content = yaml_content.encode()
        mock_workflow = MagicMock()
        mock_workflow.path = ".github/workflows/ci.yml"
        mock_repo = MagicMock()
        mock_repo.get_workflows.return_value = [mock_workflow]
        mock_repo.get_contents.return_value = mock_content
        tools.client.get_repo.return_value = mock_repo

        actions = tools.get_workflow_action_names("owner/repo", ".github/workflows/ci.yml")
        assert "actions/checkout@v4" in actions


class TestGetGithubWorkflowFilenames:
    def test_local_repo_returns_yml_files(self, tools, local_repo):
        paths = tools._get_github_workflow_filenames(str(local_repo))
        assert any(p.endswith("ci.yml") for p in paths)

    def test_local_repo_empty_workflows_dir(self, tools, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".github" / "workflows").mkdir(parents=True)
        paths = tools._get_github_workflow_filenames(str(tmp_path))
        assert paths == set()

    def test_remote_repo_returns_paths_from_api(self, tools):
        mock_workflow = MagicMock()
        mock_workflow.path = ".github/workflows/ci.yml"
        tools.client.get_repo.return_value.get_workflows.return_value = [mock_workflow]
        paths = tools._get_github_workflow_filenames("owner/repo")
        assert ".github/workflows/ci.yml" in paths

    def test_remote_repo_caches_result(self, tools):
        mock_workflow = MagicMock()
        mock_workflow.path = ".github/workflows/ci.yml"
        tools.client.get_repo.return_value.get_workflows.return_value = [mock_workflow]
        tools._get_github_workflow_filenames("owner/repo")
        tools._get_github_workflow_filenames("owner/repo")
        tools.client.get_repo.assert_called_once()

    def test_dot_prefix_path_raises(self, tools):
        with pytest.raises(ValueError, match="not a local repo"):
            tools._get_github_workflow_filenames("./local-but-no-git")


class TestGetWorkflowFileContent:
    def test_local_repo_reads_file(self, tools, local_repo):
        path = str(local_repo / ".github" / "workflows" / "ci.yml")
        content = tools._get_workflow_file_content(str(local_repo), path)
        assert "actions/checkout" in content

    def test_remote_repo_returns_decoded_content(self, tools):
        mock_content = MagicMock()
        mock_content.decoded_content = SAMPLE_WORKFLOW.encode()
        mock_workflow = MagicMock()
        mock_workflow.path = ".github/workflows/ci.yml"
        mock_repo = MagicMock()
        mock_repo.get_workflows.return_value = [mock_workflow]
        mock_repo.get_contents.return_value = mock_content
        tools.client.get_repo.return_value = mock_repo

        content = tools._get_workflow_file_content("owner/repo", ".github/workflows/ci.yml")
        assert b"actions/checkout" in content

    def test_remote_repo_not_found_raises_file_not_found(self, tools):
        mock_workflow = MagicMock()
        mock_workflow.path = ".github/workflows/ci.yml"
        mock_repo = MagicMock()
        mock_repo.get_workflows.return_value = [mock_workflow]
        mock_repo.get_contents.side_effect = _unknown_object_exception()
        tools.client.get_repo.return_value = mock_repo

        with pytest.raises(FileNotFoundError):
            tools._get_workflow_file_content("owner/repo", ".github/workflows/ci.yml")


class TestUpdateActions:
    def test_local_repo_updates_file(self, tools, local_repo):
        path = str(local_repo / ".github" / "workflows" / "ci.yml")
        updates = [ActionVersion("actions/checkout", "v3.5.0", "v4.0.0")]
        tools.update_actions(str(local_repo), path, updates, "chore: update")

        content = (local_repo / ".github" / "workflows" / "ci.yml").read_text()
        assert "actions/checkout@v4.0.0" in content
        assert "actions/checkout@v3.5.0" not in content

    def test_skips_update_when_latest_is_none(self, tools, local_repo):
        path = str(local_repo / ".github" / "workflows" / "ci.yml")
        updates = [ActionVersion("actions/checkout", "v3.5.0", None)]
        tools.update_actions(str(local_repo), path, updates, "chore: update")

        content = (local_repo / ".github" / "workflows" / "ci.yml").read_text()
        assert "actions/checkout@v3.5.0" in content

    def test_multiple_updates_applied(self, tools, local_repo):
        path = str(local_repo / ".github" / "workflows" / "ci.yml")
        updates = [
            ActionVersion("actions/checkout", "v3.5.0", "v4.0.0"),
            ActionVersion("actions/setup-python", "v4.0.0", "v5.0.0"),
        ]
        tools.update_actions(str(local_repo), path, updates, "chore: update")

        content = (local_repo / ".github" / "workflows" / "ci.yml").read_text()
        assert "actions/checkout@v4.0.0" in content
        assert "actions/setup-python@v5.0.0" in content

    def test_remote_repo_calls_github_update_file(self, tools):
        mock_content = MagicMock()
        mock_content.decoded_content = SAMPLE_WORKFLOW.encode()
        mock_content.sha = "deadbeef"
        mock_workflow = MagicMock()
        mock_workflow.path = ".github/workflows/ci.yml"
        mock_repo = MagicMock()
        mock_repo.get_workflows.return_value = [mock_workflow]
        mock_repo.get_contents.return_value = mock_content
        tools.client.get_repo.return_value = mock_repo

        updates = [ActionVersion("actions/checkout", "v3.5.0", "v4.0.0")]
        tools.update_actions("owner/repo", ".github/workflows/ci.yml", updates, "chore: update")

        mock_repo.update_file.assert_called_once()
        _, kwargs = mock_repo.update_file.call_args
        # positional: path, message, content, sha
        call_args = mock_repo.update_file.call_args[0]
        assert "actions/checkout@v4.0.0" in call_args[2]


class TestUtf8Encoding:
    """Regression tests for Windows cp1252 encoding crash (issue #5)."""

    def test_reads_utf8_workflow_file(self, tools, tmp_path):
        (tmp_path / ".git").mkdir()
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)
        utf8_workflow = "name: Ünïcödé CI\non: [push]\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n"
        wf_path = workflows_dir / "ci.yml"
        wf_path.write_text(utf8_workflow, encoding="utf-8")

        content = tools._get_workflow_file_content(str(tmp_path), str(wf_path))
        assert "Ünïcödé" in content

    def test_writes_utf8_workflow_file(self, tools, tmp_path):
        (tmp_path / ".git").mkdir()
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)
        wf_path = workflows_dir / "ci.yml"
        wf_path.write_text(SAMPLE_WORKFLOW, encoding="utf-8")

        updates = [ActionVersion("actions/checkout", "v3.5.0", "v4.0.0")]
        tools.update_actions(str(tmp_path), str(wf_path), updates, "chore: update")

        written = wf_path.read_text(encoding="utf-8")
        assert "actions/checkout@v4.0.0" in written


class TestGetRepoWorkflowNames:
    def test_local_repo_extracts_name_from_yaml(self, tools, local_repo):
        names = tools.get_repo_workflow_names(str(local_repo))
        path_key = str(local_repo / ".github" / "workflows" / "ci.yml")
        assert path_key in names
        assert names[path_key] == "CI"

    def test_remote_repo_extracts_name(self, tools):
        mock_content = MagicMock()
        mock_content.decoded_content = SAMPLE_WORKFLOW.encode()
        mock_workflow = MagicMock()
        mock_workflow.path = ".github/workflows/ci.yml"
        mock_repo = MagicMock()
        mock_repo.get_workflows.return_value = [mock_workflow]
        mock_repo.get_contents.return_value = mock_content
        tools.client.get_repo.return_value = mock_repo

        names = tools.get_repo_workflow_names("owner/repo")
        assert names[".github/workflows/ci.yml"] == "CI"

    def test_workflow_without_name_falls_back_to_path(self, tools, local_repo):
        no_name_yaml = "on: [push]\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps: []\n"
        (local_repo / ".github" / "workflows" / "no-name.yml").write_text(no_name_yaml)
        names = tools.get_repo_workflow_names(str(local_repo))
        no_name_path = str(local_repo / ".github" / "workflows" / "no-name.yml")
        assert names[no_name_path] == no_name_path
