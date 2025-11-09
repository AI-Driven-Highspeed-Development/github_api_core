# GitHub API Core

Lightweight helper built around the GitHub CLI for cloning repositories and fetching single files.

## Overview
- Requires the `gh` CLI; enforces install and login checks on initialization.
- Accepts repository references in SSH, HTTPS, or bare `owner/repo` form.
- Resolves the canonical `nameWithOwner` and default branch through `gh repo view`.
- Exposes a clone helper with automatic temp directory management and optional callbacks.

## Features
- CLI-backed clone with optional `clone_args` override and callback cleanup flow.
- Single-file fetch using `gh api` with raw response support.
- Temporary directories handled via `TempFilesManager`; automatic cleanup for callback workflows.
- Optional token forwarding for raw API usage via `token` param or `GITHUB_TOKEN`.

## Quickstart

Clone into a managed temp directory and process it immediately:

```python
from cores.github_api_core import GithubApi

api = GithubApi()
repo = api.repo("https://github.com/octocat/Hello-World")

def inspect(path: str) -> None:
	print("Files:")
	for entry in sorted(Path(path).iterdir()):
		print(" -", entry.name)

repo.clone_repo(callback=inspect)
```

Clone with a destination and retain the working tree:

```python
from cores.github_api_core import GithubApi

api = GithubApi()
repo = api.repo("git@github.com:github/gitignore.git")
dest = repo.clone_repo(dest_path="./cache/gitignore", clone_args=["--depth=1"])
# Work with files under ./cache/gitignore
```

Fetch a single file as text:

```python
from cores.github_api_core import GithubApi

api = GithubApi()
repo = api.repo("github/gitignore", branch="main")
license_text = repo.get_file("LICENSE")
```

## API

```python
class GithubApi:
	def __init__(self, *, token: str | None = None, temp_mgr: TempFilesManager | None = None, timeout: int = 15) -> None: ...
	def repo(self, url: str, branch: str | None = None) -> GithubRepo: ...
	def create_repo(self, name_with_owner: str, *, private: bool = False, description: str | None = None) -> bool: ...
	def get_user_orgs(self) -> list[dict[str, Any]]: ...

class GithubRepo:
	def clone_repo(
		self,
		dest_path: str | None = None,
		*,
		callback: Callable[[str], Any] | None = None,
		clone_args: list[str] | None = None,
	) -> Any: ...

	def get_file(self, relative_path: str, *, encoding: str = "utf-8") -> str | None: ...
	def get_file_bytes(self, relative_path: str) -> bytes | None: ...
	def cleanup_temp(self, path: str) -> None: ...
```

Notes
- Supply either `dest_path` or `callback` when cloning; when both are provided the callback receives the persisted path.
- Default clone uses `--depth=1`; pass `clone_args=[]` to fetch full history.
- Errors from `gh` include CLI stderr for easier debugging.

## Requirements & prerequisites
- GitHub CLI (`gh`) installed and authenticated against `github.com`.
- Git ≥ 2.25 available on PATH (provided by `gh` installations on most systems).
- Python dependencies listed in `requirements.txt`: `GitPython`, `requests`.
- Network access to `github.com` and `raw.githubusercontent.com`.

## Troubleshooting
- `RuntimeError` mentioning install instructions: install the GitHub CLI and retry.
- `RuntimeError` referencing authentication: run `gh auth login --hostname github.com --git-protocol https --web` followed by `gh auth status`.
- Clone command exits with non-zero status: inspect the logged stderr for missing scopes or repository permissions.
- Callback cleans the directory before you finish: provide a `dest_path` if you need the clone after the callback returns.

## Module structure

```
cores/github_api_core/
├─ __init__.py        # exports GithubApi and GithubRepo
├─ api.py             # CLI-backed implementation
├─ url_utils.py       # user guidance constants for gh setup
├─ fetch_https.py     # legacy raw HTTPS helpers
├─ fetch_ssh.py       # legacy sparse checkout helpers
├─ requirements.txt   # module-specific deps (GitPython, requests)
└─ README.md          # this file
```

## See also
- Temp Files Manager: centralized temp directory creation and cleanup utilities.
- YAML Reading Core: parse and validate text retrieved from GitHub repositories.
