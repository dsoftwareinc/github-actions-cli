GitHub Actions CLI
====================

The purpose of this tool is to work with your GitHub Actions workflows in your repositories.
It is complementary to the GitHub CLI.

It is important `GITHUB_TOKEN` environment variable is set in order for it to work properly.

So far, three main flows are supported:

# List all workflows path and name in a specified repository.

Example:

```shell
github-actions-cli -repo cunla/fakeredis list-workflows
```

will return:

```text
.github/workflows/publish.yml
.github/workflows/test.yml
```

# List all actions `uses` in a workflow

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

# Update all actions in a repository workflows
List the latest versions of actions used in a repository workflow and update the workflow files.

Example for local clone of repository:
```shell
github-actions-cli update-actions --dry-run
```

or for remote repository without cloning:

```shell
github-actions-cli -repo cunla/fakeredis update-actions --dry-run
```

Result:
```text
./.github/workflows/test.yml:
	release-drafter/release-drafter    v5 ==> v5.24.0
	actions/checkout                  v3 ==> v3.5.3
	actions/setup-python              v4 ==> v4.7.0
./.github/workflows/publish.yml:
	pypa/gh-action-pypi-publish    release/v1 ==> v1.8.8
	actions/checkout                  v3 ==> v3.5.3
	actions/setup-python              v4 ==> v4.7.0
```

# Installation

```shell
pip install github-actions-cli
```

# Help messages

```text
Usage: github-actions-cli [OPTIONS] COMMAND [ARGS]...

Options:
  -repo TEXT           Repository to analyze
  --github-token TEXT  GitHub token to use, by default will use GITHUB_TOKEN
                       environment variable
  --help               Show this message and exit.

Commands:
  list-actions    List actions in a workflow
  list-workflows  List workflows in repository
  update-actions  List actions in a workflow
```
