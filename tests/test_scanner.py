"""Tests for scanner data classes and CSV serialization."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from gha_cli.scanner import CsvClass, Org, Repo, print_orgs_as_csvs


@dataclass
class SimpleCsv(CsvClass):
    field_a: str
    field_b: int


@dataclass
class CsvWithIgnore(CsvClass):
    IGNORE_FIELDS = ["hidden"]
    visible: str
    hidden: str


class TestCsvClass:
    def test_get_attributes_returns_all_field_names(self):
        obj = SimpleCsv(field_a="hello", field_b=42)
        assert obj.get_attributes() == ["field_a", "field_b"]

    def test_csv_header_joins_field_names(self):
        obj = SimpleCsv(field_a="hello", field_b=42)
        assert obj.csv_header() == "field_a,field_b"

    def test_csv_str_joins_values(self):
        obj = SimpleCsv(field_a="hello", field_b=42)
        assert obj.csv_str() == "hello,42"

    def test_ignore_fields_excluded_from_header(self):
        obj = CsvWithIgnore(visible="yes", hidden="secret")
        assert obj.csv_header() == "visible"

    def test_ignore_fields_excluded_from_csv_str(self):
        obj = CsvWithIgnore(visible="yes", hidden="secret")
        assert obj.csv_str() == "yes"


def _make_mock_gh_repo(
    name="my-repo",
    private=False,
    archived=False,
    branches=3,
    collaborators=5,
    commits=10,
    has_issues=True,
    pulls=2,
    size=512,
    is_template=False,
    forks=0,
):
    repo = MagicMock()
    repo.name = name
    repo.private = private
    repo.archived = archived
    repo.get_branches.return_value.totalCount = branches
    repo.get_collaborators.return_value.totalCount = collaborators
    repo.get_commits.return_value.totalCount = commits
    repo.has_issues = has_issues
    repo.get_pulls.return_value.totalCount = pulls
    repo.size = size
    repo.is_template = is_template
    repo.forks_count = forks
    return repo


class TestRepo:
    def test_basic_fields_mapped_correctly(self):
        r = Repo.from_github_repo(_make_mock_gh_repo())
        assert r.name == "my-repo"
        assert r.is_private is False
        assert r.is_archived is False
        assert r.branches_count == 3
        assert r.collaborators_count == 5
        assert r.has_issues is True
        assert r.size == 512
        assert r.is_template is False
        assert r.forks_count == 0

    def test_active_when_recent_commits_exist(self):
        r = Repo.from_github_repo(_make_mock_gh_repo(commits=5))
        assert r.is_active is True

    def test_inactive_when_no_recent_commits(self):
        r = Repo.from_github_repo(_make_mock_gh_repo(commits=0))
        assert r.is_active is False

    def test_has_pull_requests_true(self):
        r = Repo.from_github_repo(_make_mock_gh_repo(pulls=3))
        assert r.has_pull_requests is True

    def test_has_pull_requests_false(self):
        r = Repo.from_github_repo(_make_mock_gh_repo(pulls=0))
        assert r.has_pull_requests is False

    def test_large_repo_flag_above_threshold(self):
        r = Repo.from_github_repo(_make_mock_gh_repo(size=2 * 1024 * 1024))
        assert r.large_repo is True

    def test_large_repo_flag_below_threshold(self):
        r = Repo.from_github_repo(_make_mock_gh_repo(size=512))
        assert r.large_repo is False

    def test_csv_str_contains_repo_name(self):
        r = Repo.from_github_repo(_make_mock_gh_repo(name="my-repo"))
        assert "my-repo" in r.csv_str()


def _make_mock_gh_org(name="my-org", members=10, teams=3, gh_repos=None):
    org = MagicMock()
    org.name = name
    org.get_members.return_value.totalCount = members
    org.get_teams.return_value.totalCount = teams
    org.get_repos.return_value = gh_repos or []
    return org


class TestOrg:
    def test_basic_fields_mapped_correctly(self):
        org = Org.from_github_org(_make_mock_gh_org())
        assert org.name == "my-org"
        assert org.members_count == 10
        assert org.teams_count == 3

    def test_empty_org_has_zero_repo_count(self):
        org = Org.from_github_org(_make_mock_gh_org())
        assert org.repositories_count == 0
        assert org.repositories == []

    def test_repositories_count_matches_repos(self):
        gh_repos = [_make_mock_gh_repo("r1"), _make_mock_gh_repo("r2")]
        org = Org.from_github_org(_make_mock_gh_org(gh_repos=gh_repos))
        assert org.repositories_count == 2
        assert len(org.repositories) == 2

    def test_repositories_field_excluded_from_csv_header(self):
        org = Org.from_github_org(_make_mock_gh_org())
        # "repositories" must not appear as a standalone column (repositories_count is allowed)
        assert "repositories" not in org.csv_header().split(",")

    def test_csv_header_has_expected_columns(self):
        org = Org.from_github_org(_make_mock_gh_org())
        header = org.csv_header()
        assert "name" in header
        assert "members_count" in header
        assert "teams_count" in header
        assert "repositories_count" in header

    def test_csv_str_contains_org_name(self):
        org = Org.from_github_org(_make_mock_gh_org(name="acme"))
        assert "acme" in org.csv_str()


class TestPrintOrgsAsCsvs:
    def test_empty_list_produces_no_output(self, capsys):
        print_orgs_as_csvs([])
        assert capsys.readouterr().out == ""

    def test_outputs_header_row(self, capsys):
        org = Org.from_github_org(_make_mock_gh_org(name="testorg"))
        print_orgs_as_csvs([org])
        lines = capsys.readouterr().out.splitlines()
        assert any("name" in line for line in lines)

    def test_outputs_data_row_with_org_name(self, capsys):
        org = Org.from_github_org(_make_mock_gh_org(name="testorg"))
        print_orgs_as_csvs([org])
        lines = capsys.readouterr().out.splitlines()
        assert any("testorg" in line for line in lines)

    def test_org_with_repos_outputs_repo_csv(self, capsys):
        gh_repos = [_make_mock_gh_repo("repo1")]
        org = Org.from_github_org(_make_mock_gh_org(gh_repos=gh_repos))
        print_orgs_as_csvs([org])
        output = capsys.readouterr().out
        assert "repo1" in output
