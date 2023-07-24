GitHub Actions CLI
====================

The purpose of this tool is to work with your GitHub Actions workflows in your repositories.
It is complementary to the GitHub CLI.

# Basic usage

Run `github-actions-cli` within a directory which has a clone of a GitHub repository.
The tool will list the GitHub actions workflows, the actions they use, the current versions they use, and the latest
versions of the actions.

```text
./.github/workflows/test.yml:
	actions/checkout                  v3 ==> v3.5.3
	release-drafter/release-drafter    v5 ==> v5.24.0
	actions/setup-python              v4 ==> v4.7.0
./.github/workflows/publish.yml:
	pypa/gh-action-pypi-publish    release/v1 ==> v1.8.8
	actions/checkout                  v3 ==> v3.5.3
	actions/setup-python              v4 ==> v4.7.0
```

# Supported use cases

```text
Usage: github-actions-cli [OPTIONS] COMMAND [ARGS]...

Options:
  -repo TEXT           Repository to analyze, can be a local directory or a
                       {OWNER}/{REPO} format  [default: .]
  --github-token TEXT  GitHub token to use, by default will use GITHUB_TOKEN
                       environment variable
  --help               Show this message and exit.

Commands:
  list-actions    List actions in a workflow
  list-workflows  List workflows in repository
  update-actions  Show actions required updates in repository workflows
```

## `update-actions` List all actions that are out of date in a repository (Default)

List the latest versions of actions used in a repository workflows
and potentially update the workflow files.

For example, running `github-actions-cli` without any parameters will look for workflows in the
current directory (`.`), check whether there are updates required for the actions in the workflows
it finds.

Another example, running on a remote repository, `github-actions-cli -repo cunla/fakeredis update-actions -u`,
will look for the latest versions of the actions used in the repository cunla/fakeredis, and because of the `-u`
flag, it will create a commit updating the workflows to the latest.

> Note:
> Having `GITHUB_TOKEN` with permissions to make commits on the repository
> is required in order to write to repository.

Parameters:

```text
Usage: cli.py update-actions [OPTIONS]

  Show actions required updates in repository workflows

Options:
  -u, --update      Do not update, list only
  -commit-msg TEXT  Commit msg, only relevant when remote repo
```

## `list-workflows` List all workflows path and name in a specified repository.

Example:

```shell
github-actions-cli -repo cunla/fakeredis list-workflows
```

will return:

```text
.github/workflows/publish.yml
.github/workflows/test.yml
```

## `list-actions` List all actions `uses` in a workflow

Given a repo and a workflow path, return all actions in the workflow.

Example:

```shell
github-actions-cli -repo cunla/fakeredis list-actions .github/workflows/test.yml
```

Result

```text
actions/checkout@v3
./.github/actions/test-coverage
release-drafter/release-drafter@v5
actions/setup-python@v4
```

# Installation

```shell
pip install github-actions-cli
```
