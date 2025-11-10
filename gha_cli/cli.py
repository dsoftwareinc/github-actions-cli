#!/usr/bin/env python3
import logging
import os
from collections import namedtuple
from datetime import datetime, timezone
from typing import Optional, List, Set, Dict, Union, Any, Tuple

import click
import coloredlogs
import yaml
from github import Github, UnknownObjectException, GitRelease
from github.Organization import Organization
from github.PaginatedList import PaginatedList
from github.Repository import Repository

from gha_cli.scanner import Org, print_orgs_as_csvs

coloredlogs.install(level="INFO")
logger = logging.getLogger()

ActionVersion = namedtuple("ActionVersion", ["name", "current", "latest"])


def _is_sha(current_version: str) -> bool:
    """Check if the current version is a SHA (40 characters long)"""
    return len(current_version) == 40 and all(c in "0123456789abcdef" for c in current_version.lower())


class GithubActionsTools(object):
    _wf_cache: dict[str, dict[str, Any]] = dict()  # repo_name -> [path -> workflow/yaml]
    __actions_latest_release: dict[str, Tuple[str, datetime]] = (
        dict()
    )  # action_name@current_release -> latest_release_tag

    def __init__(self, github_token: str, update_major_version_only: bool = False):
        self.client = Github(login_or_token=github_token)
        self._update_major_version_only = update_major_version_only

    def _get_repo(self, repo_name: str) -> Repository:
        """Get a repository from github client"""
        try:
            return self.client.get_repo(repo_name)
        except UnknownObjectException:
            logging.error(f"Repository {repo_name} not found")
            raise ValueError(f"Repository {repo_name} not found")

    def _fix_version(self, tag_name: str) -> str:
        if self._update_major_version_only:
            return tag_name.split(".")[0]
        return tag_name

    def _compare_versions(self, orig_v1: str, orig_v2: str) -> int:
        """Compare two versions, return 1 if v1 > v2, 0 if v1 == v2, -1 if v1 < v2"""
        if orig_v1.startswith("v"):
            orig_v1 = orig_v1[1:]
        if orig_v2.startswith("v"):
            orig_v2 = orig_v2[1:]
        v1 = orig_v1.split(".")
        v2 = orig_v2.split(".")
        if self._update_major_version_only:
            v1 = [v1[0]]
            v2 = [v2[0]]
        compare_count = max(len(v1), len(v2))
        try:
            for i in range(compare_count):
                v1_i = int(v1[i]) if i < len(v1) else 0
                v2_i = int(v2[i]) if i < len(v2) else 0
                if v1_i > v2_i:
                    return 1
                if v1_i < v2_i:
                    return -1
        except ValueError:
            logging.warning(f"Could not compare versions {orig_v1} and {orig_v2}")
        return 0

    def get_action_latest_release(self, uses_tag_value: str) -> Optional[str]:
        """Check whether an action has an update, and return the latest version if it does syntax for uses:
        https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#jobsjob_iduses
        """
        if "@" not in uses_tag_value:
            return None
        action_name, current_version = uses_tag_value.split("@")
        if action_name in self.__actions_latest_release:
            latest_release = self.__actions_latest_release[action_name]
            logging.debug(f"Found in cache {action_name}: {latest_release}")
            if _is_sha(current_version):
                logging.debug(
                    f"Current version for {action_name} is a SHA: {current_version}, checking whether latest release is newer"
                )
                now = datetime.now(timezone.utc)
                release_time = latest_release[1]
                if release_time.tzinfo is None:
                    release_time = release_time.replace(tzinfo=timezone.utc)
                if release_time > now:
                    return latest_release[0]
            return latest_release[0] if self._compare_versions(latest_release[0], current_version) > 0 else None

        logging.debug(f"Checking for updates for {action_name}@{current_version}: Getting repo {action_name}")
        try:
            repo: Repository = self._get_repo(action_name)
        except ValueError:
            return None
        logging.info(f"Getting latest release for repository: {action_name}")
        latest_release: GitRelease
        try:
            latest_release = repo.get_latest_release()
            if latest_release is None:
                logging.warning(f"No latest release found for repository: {action_name}")
                return None
        except UnknownObjectException:
            logging.warning(f"No releases found for repository: {action_name}")

        if _is_sha(current_version):
            logging.debug(
                f"Current version for {action_name} is a SHA: {current_version}, checking whether latest release is newer"
            )
            current_version_commit = repo.get_commit(current_version)
            if latest_release.last_modified_datetime > current_version_commit.last_modified_datetime:
                self.__actions_latest_release[action_name] = (
                    self._fix_version(latest_release.tag_name),
                    latest_release.last_modified_datetime,
                )
                return latest_release.tag_name
        if self._compare_versions(latest_release.tag_name, current_version) > 0:
            self.__actions_latest_release[action_name] = (
                self._fix_version(latest_release.tag_name),
                latest_release.last_modified_datetime,
            )
            return latest_release.tag_name
        return None

    @staticmethod
    def is_local_repo(repo_name: str) -> bool:
        return os.path.exists(repo_name) and os.path.exists(os.path.join(repo_name, ".git"))

    @staticmethod
    def list_full_paths(path: str) -> set[str]:
        if not os.path.exists(path):
            return set()
        return {os.path.join(path, file) for file in os.listdir(path) if file.endswith((".yml", ".yaml"))}

    def get_workflow_action_names(self, repo_name: str, workflow_path: str) -> Set[str]:
        workflow_content = self._get_workflow_file_content(repo_name, workflow_path)
        workflow = yaml.safe_load(workflow_content)
        res = set()
        for job in workflow.get("jobs", dict()).values():
            for step in job.get("steps", list()):
                if "uses" in step:
                    res.add(step["uses"])
        return res

    def get_repo_actions_latest(self, repo_name: str) -> Dict[str, List[ActionVersion]]:
        workflow_paths = self._get_github_workflow_filenames(repo_name)
        res: Dict[str, List[ActionVersion]] = dict()
        actions_per_path: Dict[str, Set[str]] = dict()  # actions without version, e.g., actions/checkout
        for path in workflow_paths:
            res[path] = list()
            actions = self.get_workflow_action_names(repo_name, path)
            for action in actions:
                actions_per_path.setdefault(path, set()).add(action)
        all_actions_no_version = set()
        for path, actions in actions_per_path.items():
            for action in actions:
                if "@" not in action:
                    continue
                all_actions_no_version.add(action.split("@")[0])
        logging.info(f"Found {len(all_actions_no_version)} actions in workflows: {', '.join(all_actions_no_version)}")
        for path, actions in actions_per_path.items():
            for action in actions:
                if "@" not in action:
                    continue
                action_name, curr_version = action.split("@")
                latest_version = self.get_action_latest_release(action)
                res[path].append(ActionVersion(action_name, curr_version, latest_version))
        return res

    def get_repo_workflow_names(self, repo_name: str) -> Dict[str, str]:
        workflow_paths = self._get_github_workflow_filenames(repo_name)
        res = dict()
        for path in workflow_paths:
            try:
                content = self._get_workflow_file_content(repo_name, path)
                yaml_content = yaml.safe_load(content)
                res[path] = yaml_content.get("name", path)
            except FileNotFoundError as ex:
                logging.warning(ex)
        return res

    def update_actions(
        self,
        repo_name: str,
        workflow_path: str,
        updates: List[ActionVersion],
        commit_msg: str,
    ) -> None:
        workflow_content = self._get_workflow_file_content(repo_name, workflow_path)
        if isinstance(workflow_content, bytes):
            workflow_content = workflow_content.decode()
        for update in updates:
            if update.latest is None:
                continue
            current_action = f"{update.name}@{update.current}"
            latest_action = f"{update.name}@{update.latest}"
            workflow_content = workflow_content.replace(current_action, latest_action)
        self._update_workflow_content(repo_name, workflow_path, workflow_content, commit_msg)

    def _update_workflow_content(self, repo_name: str, workflow_path: str, workflow_content: str, commit_msg: str):
        if self.is_local_repo(repo_name):
            with open(workflow_path, "w") as f:
                f.write(workflow_content)
            click.secho(f"Updated workflow in {workflow_path}", fg="cyan")
            return

        # remote
        repo: Repository = self._get_repo(repo_name)
        current_content = repo.get_contents(workflow_path)
        res = repo.update_file(
            workflow_path,
            commit_msg,
            workflow_content,
            current_content.sha,
        )
        click.secho(f"Committed changes to workflow in {repo_name}:{workflow_path}", fg="cyan")
        return res

    def _get_github_workflow_filenames(self, repo_name: str) -> Set[str]:
        if repo_name in self._wf_cache:
            return set(self._wf_cache[repo_name].keys())
        # local
        if self.is_local_repo(repo_name):
            return self.list_full_paths(os.path.join(repo_name, ".github", "workflows"))
        if repo_name.startswith("."):
            click.secho(f"{repo_name} is not a local repo and does not start with owner/repo", fg="red", err=True)
            raise ValueError(f"{repo_name} is not a local repo and does not start with owner/repo")
        # Remote
        repo: Repository = self._get_repo(repo_name)
        self._wf_cache[repo_name] = {wf.path: wf for wf in repo.get_workflows() if wf.path.startswith(".github/")}
        return set(self._wf_cache[repo_name].keys())

    def _get_workflow_file_content(self, repo_name: str, workflow_path: str) -> Union[str, bytes]:
        workflow_paths = self._get_github_workflow_filenames(repo_name)

        if self.is_local_repo(repo_name):
            if not os.path.exists(workflow_path):
                click.echo(
                    f"f{workflow_path} not found in workflows for repository {repo_name}, "
                    f"possible values: {workflow_paths}",
                    err=True,
                )
            with open(workflow_path) as f:
                return f.read()

        if workflow_path not in workflow_paths:
            click.echo(
                f"f{workflow_path} not found in workflows for repository {repo_name}, "
                f"possible values: {workflow_paths}",
                err=True,
            )
        try:
            repo: Repository = self._get_repo(repo_name)
            workflow_content = repo.get_contents(workflow_path)
        except UnknownObjectException:
            raise FileNotFoundError(f"Workflow not found in repository: {repo_name}, path: {workflow_path}")
        return workflow_content.decoded_content


GITHUB_ACTION_NOT_PROVIDED_MSG = """GitHub connection token not provided.
You might not be able to make the changes to remote repositories.
You can provide it using GITHUB_TOKEN environment variable or --github-token option.
"""


@click.group(invoke_without_command=True)
@click.option(
    "-v", "--verbose", count=True, help="Increase verbosity, can be used multiple times to increase verbosity"
)
@click.option(
    "--repo",
    default=".",
    show_default=True,
    type=str,
    help="Repository to analyze, can be a local directory or a {OWNER}/{REPO} format",
)
@click.option(
    "--github-token",
    default=os.getenv("GITHUB_TOKEN"),
    type=str,
    show_default=False,
    help="GitHub token to use, by default will use GITHUB_TOKEN environment variable",
)
@click.option(
    "-m",
    "--major-only",
    is_flag=True,
    default=False,
    help="Update major versions only, e.g., v1.2.3 will not be upgraded to v1.2.4 but to v2",
)
@click.pass_context
def cli(ctx, verbose: int, repo: str, github_token: Optional[str], major_only: bool):
    if verbose == 1:
        coloredlogs.install(level="INFO")
    if verbose > 1:
        coloredlogs.install(level="DEBUG")
    ctx.ensure_object(dict)
    repo_name = os.getcwd() if repo == "." else repo
    click.secho(f"GitHub Actions CLI, scanning repo in {repo_name}", fg="green", bold=True)
    if not github_token:
        click.secho(GITHUB_ACTION_NOT_PROVIDED_MSG, fg="yellow", err=True)
    ctx.obj["gh"] = GithubActionsTools(github_token, major_only)
    ctx.obj["repo"] = repo
    if not ctx.invoked_subcommand:
        ctx.invoke(update_actions)


@cli.command(help="Show actions required updates in repository workflows")
@click.option(
    "-u",
    "--update",
    is_flag=True,
    default=False,
    help="Update actions in workflows (For remote repos: make changes and commit, for local repos: update files",
)
@click.option(
    "-commit-msg",
    default="chore(ci):update actions",
    type=str,
    show_default=True,
    help="Commit msg, only relevant when remote repo",
)
@click.pass_context
def update_actions(ctx, update: bool, commit_msg: str) -> None:
    gh, repo_name = ctx.obj["gh"], ctx.obj["repo"]
    workflow_names = gh.get_repo_workflow_names(repo_name)
    logging.info(f"Found {len(workflow_names)} workflows in {repo_name}: {', '.join(list(workflow_names.keys()))}")
    workflow_action_versions = gh.get_repo_actions_latest(repo_name)
    max_action_name_length, max_version_length = 0, 0
    for workflow_path, actions in workflow_action_versions.items():
        for action in workflow_action_versions[workflow_path]:
            max_action_name_length = max(max_action_name_length, len(action.name))
            max_version_length = max(max_version_length, len(action.current))
    for workflow_path, workflow_name in workflow_names.items():
        click.secho(f"{workflow_path} ({click.style(workflow_name, fg='bright_cyan')}):", fg="bright_blue")
        for action in workflow_action_versions[workflow_path]:
            s = f"\t{action.name:<{max_action_name_length + 5}} {action.current:>{max_version_length + 2}}"
            if action.latest:
                old_version = action.current.split(".")
                new_version = action.latest.split(".")
                color = "red" if new_version[0] != old_version[0] else "cyan"
                s += " ==> " + click.style(f"{action.latest}", fg=color)
            click.echo(s)
    if not update:
        return
    for workflow in workflow_action_versions:
        gh.update_actions(repo_name, workflow, workflow_action_versions[workflow], commit_msg)


@cli.command(help="List actions in a workflow")
@click.argument("workflow")
@click.pass_context
def list_actions(ctx, workflow: str):
    actions = ctx.obj["gh"].get_workflow_action_names(ctx.obj["repo"], workflow)
    for action in actions:
        click.echo(action)


@cli.command(help="List workflows in repository")
@click.pass_context
def list_workflows(ctx):
    workflow_paths = ctx.obj["gh"].get_repo_workflow_names(ctx.obj["repo"])
    for path, name in workflow_paths.items():
        click.echo(f"{path} - {name}")


@cli.command(help="Analyze organizations")
@click.option("-x", "--exclude", multiple=True, default=[], help="Exclude orgs")
@click.pass_context
def analyze_orgs(ctx, exclude: Set[str] = None):
    gh_client: Github = ctx.obj["gh"].client
    exclude = exclude or {}
    exclude = set(exclude)
    current_user = gh_client.get_user()
    gh_orgs: PaginatedList[Organization] = current_user.get_orgs()
    logging.info(f"Analyzing {gh_orgs.totalCount} organizations")
    orgs: List[Org] = []
    for gh_org in gh_orgs:
        if gh_org.login in exclude:
            continue
        org = Org.from_github_org(gh_org)
        orgs.append(org)
    print_orgs_as_csvs(orgs)


if __name__ == "__main__":
    cli(obj={})
