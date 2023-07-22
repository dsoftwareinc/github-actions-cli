import argparse
import os
from typing import Optional, List, Set, Tuple, Dict

import yaml
from github import Github, Workflow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('repo', help='Repository to analyze')
    parser.add_argument(
        '--github-token', dest='github_token', default=None,
        help='GitHub token to use, by default will use GITHUB_TOKEN environment variable')
    subcommands = parser.add_subparsers(dest='command', required=True)
    list_wfs_cmd_parser = subcommands.add_parser('list-workflows', help='List github workflows')
    list_wfs_cmd_parser.add_argument('--local-only', action='store_true', dest='local_only',
                                     help='Show only workflows stored in the repository')
    list_actions_cmd_parser = subcommands.add_parser('list-actions', help='List actions in a workflow')
    list_actions_cmd_parser.add_argument('workflow_path', help='Workflow path')
    update_gha_cmd_parser = subcommands.add_parser('update', help='Update actions in github workflows')
    update_gha_cmd_parser.add_argument("--dry-run", action='store_true', dest='dryrun', help='List updates only')
    return parser.parse_args()


class GithubActionsTools(object):
    workflows: dict[str, dict[str, Workflow]] = dict()  # repo_name -> [path -> workflow]
    actions: dict[str, str] = dict()  # action_name -> latest_release_tag

    def __init__(self, github_token: Optional[str]):
        github_token = github_token or os.getenv('GITHUB_TOKEN')
        if github_token is None:
            raise ValueError('GITHUB_TOKEN must be set')
        self.client = Github(login_or_token=github_token)

    def get_github_workflows(self, repo_name: str, local_only: bool = False) -> List[Workflow]:
        if repo_name in self.workflows:
            return list(self.workflows[repo_name].values())
        repo = self.client.get_repo(repo_name)
        workflows = list(repo.get_workflows())
        if local_only:
            workflows = list(filter(lambda item: item.path.startswith('.github/'), workflows))
        self.workflows[repo_name] = {wf.path: wf for wf in workflows}
        return workflows

    def get_workflow_actions(self, repo_name: str, workflow_path: str) -> Set[str]:

        self.get_github_workflows(repo_name)
        if workflow_path not in self.workflows[repo_name]:
            raise ValueError(f'f{workflow_path} not found in workflows for repository {repo_name}, '
                             f'possible values: {self.workflows[repo_name].keys()}')
        repo = self.client.get_repo(repo_name)
        workflow_content = repo.get_contents(workflow_path)
        workflow = yaml.load(workflow_content.decoded_content, Loader=yaml.CLoader)
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

    def get_repo_actions_latest(self, repo_name: str) -> Dict[str, List[Tuple[str, str, Optional[str]]]]:
        workflows = self.get_github_workflows(repo_name)
        res = dict()
        for workflow in workflows:
            if not workflow.path.startswith('.github'):
                continue
            res[workflow.path] = list()
            actions = self.get_workflow_actions(repo_name, workflow.path)
            for action in actions:
                if '@' not in action:
                    continue
                action_name, curr_version = action.split('@')
                latest = self.check_for_updates(action)
                res[workflow.path].append((action_name, curr_version, latest))
        return res


def run():
    args = parse_args()
    gh = GithubActionsTools(args.github_token)
    gh.check_for_updates('actions/checkout@v2')
    if args.command == 'list-workflows':
        workflows = gh.get_github_workflows(args.repo)
        for workflow in workflows:
            print(f'{workflow.path}:{workflow.name}')
    elif args.command == 'list-actions':
        actions = gh.get_workflow_actions(args.repo, args.workflow_path)
        for action in actions:
            print(action)
    elif args.command == 'update':
        action_versions = gh.get_repo_actions_latest(args.repo)
        for wf in action_versions:
            print(f'{wf}:')
            for action in action_versions[wf]:
                s = f'  {action[0]} @ {action[1]}'
                if action[2]:
                    s += f' \t==> {action[2]}'
                print(s)


if __name__ == '__main__':
    run()
