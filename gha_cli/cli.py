#!/usr/bin/env python3
import logging
import os
from collections import namedtuple
from typing import Optional, List, Set, Dict, Union

import click
import yaml
from github import Github, Workflow

logging.basicConfig(level=logging.WARNING)
logging.getLogger('github.Requester').setLevel(logging.WARNING)
logger = logging.getLogger()

ActionVersion = namedtuple('ActionVersion', ['name', 'current', 'latest'])


class GithubActionsTools(object):
    workflows: dict[str, dict[str, Workflow]] = dict()  # repo_name -> [path -> workflow]
    actions_latest_release: dict[str, str] = dict()  # action_name@current_release -> latest_release_tag

    def __init__(self, github_token: str):
        self.client = Github(login_or_token=github_token)

    @staticmethod
    def is_local_repo(repo_name: str) -> bool:
        return os.path.exists(repo_name)

    @staticmethod
    def list_full_paths(path: str) -> set[str]:
        return {os.path.join(path, file)
                for file in os.listdir(path)
                if file.endswith(('.yml', '.yaml'))}

    def get_github_workflows(self, repo_name: str) -> Set[str]:
        if repo_name in self.workflows:
            return set(self.workflows[repo_name].keys())
        # local
        if self.is_local_repo(repo_name):
            return self.list_full_paths(os.path.join(repo_name, '.github', 'workflows'))
        # Remote
        repo = self.client.get_repo(repo_name)
        self.workflows[repo_name] = {
            wf.path: wf
            for wf in repo.get_workflows()
            if wf.path.startswith('.github/')}
        return set(self.workflows[repo_name].keys())

    def _get_workflow_content(self, repo_name: str, workflow_path: str) -> Union[str, bytes]:
        workflow_paths = self.get_github_workflows(repo_name)

        if self.is_local_repo(repo_name):
            if not os.path.exists(workflow_path):
                click.echo(
                    f'f{workflow_path} not found in workflows for repository {repo_name}, '
                    f'possible values: {workflow_paths}', err=True)
            with open(workflow_path) as f:
                return f.read()

        if workflow_path not in workflow_paths:
            click.echo(
                f'f{workflow_path} not found in workflows for repository {repo_name}, '
                f'possible values: {workflow_paths}', err=True)
        repo = self.client.get_repo(repo_name)
        workflow_content = repo.get_contents(workflow_path)
        return workflow_content.decoded_content

    def get_workflow_actions(self, repo_name: str, workflow_path: str) -> Set[str]:
        workflow_content = self._get_workflow_content(repo_name, workflow_path)
        workflow = yaml.load(workflow_content, Loader=yaml.CLoader)
        res = set()
        for job in workflow.get('jobs', dict()).values():
            for step in job.get('steps', list()):
                if 'uses' in step:
                    res.add(step['uses'])
        return res

    def check_for_updates(self, action_name: str) -> Optional[str]:
        """Check whether an action has update, and return the latest version if it does
        syntax for uses:
        https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#jobsjob_iduses
        """
        if '@' not in action_name:
            return None
        repo_name, current_version = action_name.split('@')
        repo = self.client.get_repo(repo_name)
        latest_release = repo.get_latest_release()
        return latest_release.tag_name if latest_release.tag_name != current_version else None

    def get_repo_actions_latest(self, repo_name: str) -> Dict[str, List[ActionVersion]]:
        workflow_paths = self.get_github_workflows(repo_name)
        res = dict()
        for path in workflow_paths:
            res[path] = list()
            actions = self.get_workflow_actions(repo_name, path)
            for action in actions:
                if '@' not in action:
                    continue
                action_name, curr_version = action.split('@')
                if action not in self.actions_latest_release:
                    latest = self.check_for_updates(action)
                    self.actions_latest_release[action] = latest
                else:
                    latest = self.actions_latest_release[action]
                res[path].append(ActionVersion(action_name, curr_version, latest))
        return res

    def update_actions(
            self, repo_name: str, workflow_path: str,
            updates: List[ActionVersion],
            commit_msg: str,
    ) -> None:
        workflow_content = self._get_workflow_content(repo_name, workflow_path)
        if isinstance(workflow_content, bytes):
            workflow_content = workflow_content.decode()
        for update in updates:
            if update.latest is None:
                continue
            current_action = f'{update.name}@{update.current}'
            latest_action = f'{update.name}@{update.latest}'
            workflow_content = workflow_content.replace(current_action, latest_action)
        self._update_workflow_content(repo_name, workflow_path, workflow_content, commit_msg)

    def _update_workflow_content(
            self, repo_name: str, workflow_path: str, workflow_content: str, commit_msg: str):
        if self.is_local_repo(repo_name):
            with open(workflow_path, 'w') as f:
                f.write(workflow_content)
            click.secho(f'Updated workflow in {workflow_path}', fg='cyan')
            return

        # remote
        repo = self.client.get_repo(repo_name)
        current_content = repo.get_contents(workflow_path)
        res = repo.update_file(
            workflow_path,
            commit_msg,
            workflow_content,
            current_content.sha,
        )
        click.secho(f'Committed changes to workflow in {repo_name}:{workflow_path}', fg='cyan')
        return res


GITHUB_ACTION_NOT_PROVIDED_MSG = """GitHub connection token not provided.
You might not be able to make the changes to remote repositories.
You can provide it using GITHUB_TOKEN environment variable or --github-token option.
"""


@click.group(invoke_without_command=True)
@click.option(
    '-repo', default='.', show_default=True, type=str,
    help='Repository to analyze, can be a local directory or a {OWNER}/{REPO} format')
@click.option(
    '--github-token', default=os.getenv('GITHUB_TOKEN'), type=str, show_default=False,
    help='GitHub token to use, by default will use GITHUB_TOKEN environment variable')
@click.pass_context
def cli(ctx, repo: str, github_token: Optional[str]):
    ctx.ensure_object(dict)
    if not github_token:
        click.secho(GITHUB_ACTION_NOT_PROVIDED_MSG, fg='red', err=True)
    ctx.obj['gh'] = GithubActionsTools(github_token)
    ctx.obj['repo'] = repo
    if not ctx.invoked_subcommand:
        ctx.invoke(update_actions)


@cli.command(help='Show actions required updates in repository workflows')
@click.option('-u', '--update', is_flag=True, default=False, help='Do not update, list only')
@click.option('-commit-msg', default='Update github-actions',
              help='Commit msg, only relevant when remote repo')
@click.pass_context
def update_actions(ctx, update: bool, commit_msg: str):
    gh, repo = ctx.obj['gh'], ctx.obj['repo']
    workflow_action_versions = gh.get_repo_actions_latest(repo)
    for workflow in workflow_action_versions:
        click.secho(f'{workflow}:', fg='blue')
        for action in workflow_action_versions[workflow]:
            s = f'\t{action.name:30} {action.current:>5}'
            if action.latest:
                old_version = action.current.split('.')
                new_version = action.latest.split('.')
                color = 'red' if new_version[0] != old_version[0] else 'cyan'
                s += ' ==> ' + click.style(f'{action.latest}', fg=color)
            click.echo(s)
    if not update:
        return
    for workflow in workflow_action_versions:
        gh.update_actions(repo, workflow, workflow_action_versions[workflow], commit_msg)


@cli.command(help='List actions in a workflow')
@click.argument('workflow')
@click.pass_context
def list_actions(ctx, workflow: str):
    actions = ctx.obj['gh'].get_workflow_actions(ctx.obj['repo'], workflow)
    for action in actions:
        click.echo(action)


@cli.command(help='List workflows in repository')
@click.pass_context
def list_workflows(ctx):
    workflow_paths = ctx.obj['gh'].get_github_workflows(ctx.obj['repo'])
    for path in workflow_paths:
        click.echo(f'{path}')


if __name__ == '__main__':
    cli(obj={})
