# GitHub Actions CLI

A CLI tool for keeping GitHub Actions workflow files up to date. It works with both local repository clones and remote GitHub repositories.

## Installation

```shell
pip install github-actions-cli
```

Or run without installing via `uvx`:

```shell
uvx github-actions-cli
```

## Quick start

Run inside any local GitHub repository clone to see which actions have updates available:

```shell
github-actions-cli
```

```text
GitHub Actions CLI, scanning repo in /path/to/repo
.github/workflows/test.yml (Test):
    actions/checkout          v2 ==> v3
    actions/setup-python      v3 ==> v4
    release-drafter/release-drafter  v5
.github/workflows/publish.yml (Publish):
    pypa/gh-action-pypi-publish  v1
    actions/checkout          v2 ==> v3
```

Actions with an `==>` have a newer version available. To apply the updates, add `--update`:

```shell
github-actions-cli --update
```

## GitHub token

A `GITHUB_TOKEN` is required to query the GitHub API for the latest action versions. Set it as an environment variable or pass it with `--github-token`.

```shell
export GITHUB_TOKEN=ghp_...
github-actions-cli
```

Writing changes to a **remote** repository also requires the token to have commit permissions on that repository.

## Commands

### `update-actions` (default)

Lists actions that have updates available. Pass `--update` (`-u`) to apply the changes.

```shell
# Check for updates in the current directory
github-actions-cli

# Apply updates to local workflow files
github-actions-cli --update

# Check and update a remote repository
github-actions-cli --repo cunla/fakeredis update-actions --update

# Use a custom commit message when updating a remote repository
github-actions-cli --repo cunla/fakeredis update-actions --update -commit-msg "chore: update actions"
```

```text
Usage: github-actions-cli update-actions [OPTIONS]

Options:
  -u, --update      Apply updates to workflow files. For remote repos this
                    creates a commit; for local repos it writes the files.
  -commit-msg TEXT  Commit message (remote repos only).
                    [default: chore(ci):update actions]
  --help            Show this message and exit.
```

### `list-workflows`

Lists all workflow files found in a repository.

```shell
github-actions-cli list-workflows
github-actions-cli --repo cunla/fakeredis list-workflows
```

```text
.github/workflows/test.yml - Test
.github/workflows/publish.yml - Publish
```

### `list-actions`

Lists every action referenced in a specific workflow file.

```shell
github-actions-cli list-actions .github/workflows/test.yml
github-actions-cli --repo cunla/fakeredis list-actions .github/workflows/test.yml
```

```text
actions/checkout@v3
actions/setup-python@v4
release-drafter/release-drafter@v5
```

### `analyze-orgs`

Scans all GitHub organizations the authenticated user belongs to and prints a CSV summary of their repositories.

```shell
github-actions-cli analyze-orgs
github-actions-cli analyze-orgs --exclude my-org --exclude another-org
```

## Global options

```text
Usage: github-actions-cli [OPTIONS] COMMAND [ARGS]...

Options:
  --repo TEXT           Repository to scan. Accepts a local path or
                        owner/repo format.  [default: .]
  --github-token TEXT   GitHub token. Falls back to the GITHUB_TOKEN
                        environment variable.
  -m, --major-only      Only flag updates across major versions (e.g. v1 →
                        v2). Minor and patch bumps are ignored.
  -v, --verbose         Increase output verbosity. Pass twice for debug output.
  --help                Show this message and exit.
```
