GitHub Actions Utils
====================

The purpose of this tool is to work with your GitHub Actions workflows in your repositories.

So far, three main flows are supported:

# List all workflows path and name in a specified repository.

Example:

```shell
python ghautils.py cunla/fakeredis list-workflows
```
will return:

```text
.github/workflows/publish.yml:Upload Python Package
.github/workflows/test.yml:Unit tests
dynamic/github-code-scanning/codeql:CodeQL
dynamic/pages/pages-build-deployment:pages-build-deployment
```

# List all actions `uses` in a workflow

Given a repo and a workflow path, return all actions in the workflow.

Example:
```shell
python ghautils.py cunla/fakeredis list-actions .github/workflows/publish.yml
```

Result
```text
pypa/gh-action-pypi-publish@release/v1
actions/checkout@v3
actions/setup-python@v4
```

# Update all actions in a repository workflow(s)
Show the latest versions of actions used in a repository workflow.

Example:
```shell
python ghautils.py cunla/fakeredis update
```
Result:
```text
.github/workflows/publish.yml
  actions/setup-python @ v4     ==> v4.7.0
  pypa/gh-action-pypi-publish @ release/v1      ==> v1.8.8
  actions/checkout @ v3         ==> v3.5.3
.github/workflows/test.yml
  actions/setup-python @ v4     ==> v4.7.0
  release-drafter/release-drafter @ v5  ==> v5.24.0
  actions/checkout @ v3         ==> v3.5.3
```

# Help messages

```text
usage: ghautils.py [-h] [--github-token GITHUB_TOKEN] repo {list-workflows,list-actions,update} ...

positional arguments:
  repo                  Repository to analyze
  {list-workflows,list-actions,update}
    list-workflows      List github workflows
    list-actions        List actions in a workflow
    update              Update actions in github workflows

options:
  -h, --help            show this help message and exit
  --github-token GITHUB_TOKEN
                        GitHub token to use, by default will use GITHUB_TOKEN environment variable
```