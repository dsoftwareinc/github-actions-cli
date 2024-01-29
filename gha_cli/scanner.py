import logging
import os
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from typing import List, Optional, Set

import click
import coloredlogs
from github import Github
from github.Organization import Organization
from github.PaginatedList import PaginatedList
from github.Repository import Repository

logging.basicConfig(level=logging.INFO)
THIS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))

coloredlogs.install(level='DEBUG')


@dataclass
class CsvClass:
    IGNORE_FIELDS = []

    def get_attributes(self) -> List[str]:
        return [a.name for a in fields(self.__class__)
                if a.name not in self.IGNORE_FIELDS]

    def csv_header(self) -> str:
        return ','.join(self.get_attributes())

    def csv_str(self) -> str:
        return ','.join([str(getattr(self, attr)) for attr in self.get_attributes()])


@dataclass
class Repo(CsvClass):
    name: str
    is_private: bool
    is_archived: bool
    branches_count: int
    collaborators_count: int
    is_active: bool
    has_issues: bool
    has_pull_requests: bool
    size: int
    large_repo: bool
    is_template: bool
    forks_count: int = 0

    @classmethod
    def from_github_repo(cls, repo: Repository):
        return cls(
            name=repo.name,
            is_private=repo.private,
            is_archived=repo.archived,
            branches_count=repo.get_branches().totalCount,
            collaborators_count=repo.get_collaborators().totalCount,
            is_active=repo.get_commits(since=datetime.now() - timedelta(days=365)).totalCount > 0,
            has_issues=repo.has_issues,
            has_pull_requests=repo.get_pulls().totalCount > 0,
            size=repo.size,
            large_repo=repo.size > 1024 * 1024,
            is_template=repo.is_template,
            forks_count=repo.forks_count,
        )


@dataclass
class Org(CsvClass):
    IGNORE_FIELDS = ['repositories', ]
    name: str
    repositories: List[Repo]
    members_count: int
    teams_count: int
    repositories_count: int = 0

    def __post_init__(self):
        self.repositories_count = len(self.repositories)

    @classmethod
    def from_github_org(cls, org: Organization):
        gh_repositories: PaginatedList[Repository] = org.get_repos()
        repositories: List[Repo] = []
        for gh_repo in gh_repositories:
            repo = Repo.from_github_repo(gh_repo)
            repositories.append(repo)

        return cls(
            name=org.name,
            repositories=repositories,
            members_count=org.get_members().totalCount,
            teams_count=org.get_teams().totalCount,
        )


GITHUB_ACTION_NOT_PROVIDED_MSG = """GitHub connection token not provided.
You might not be able to make the changes to remote repositories.
You can provide it using GITHUB_TOKEN environment variable or --github-token option.
"""


@click.group(invoke_without_command=True)
@click.option(
    '--github-token', default=os.getenv('GITHUB_TOKEN'), type=str, show_default=False,
    help='GitHub token to use, by default will use GITHUB_TOKEN environment variable')
@click.pass_context
def cli(ctx, github_token: Optional[str]):
    ctx.ensure_object(dict)
    if not github_token:
        click.secho(GITHUB_ACTION_NOT_PROVIDED_MSG, fg='yellow', err=True)
        exit(1)
    ctx.obj['gh'] = Github(github_token)
    if not ctx.invoked_subcommand:
        ctx.invoke(analyze_orgs)


def _print_data(orgs: List[Org]):
    if len(orgs) == 0:
        return

    click.echo(orgs[0].csv_header())
    for org in orgs:
        click.echo(org.csv_str())

    for org in orgs:
        logging.info(f'Analyzing repos for {org.name}')
        if len(org.repositories) == 0:
            continue
        click.echo(org.repositories[0].csv_header())
        for repo in org.repositories:
            click.echo(repo.csv_str())


@cli.command(help='Analyze organizations')
@click.option('-x', '--exclude', multiple=True, default=[], help='Exclude orgs')
@click.pass_context
def analyze_orgs(ctx, exclude: Set[str] = None):
    gh_client: Github = ctx.obj['gh']
    exclude = exclude or {}
    exclude = set(exclude)
    current_user = gh_client.get_user()
    gh_orgs: PaginatedList[Organization] = current_user.get_orgs()
    logging.info(f'Analyzing {gh_orgs.totalCount} organizations')
    orgs: List[Org] = []
    for gh_org in gh_orgs:
        if gh_org.login in exclude:
            continue
        org = Org.from_github_org(gh_org)
        orgs.append(org)
    _print_data(orgs)


if __name__ == '__main__':
    # print(Org(name='test', repositories=[], members_count=1, teams_count=1).csv_header())
    cli(obj={})
