# GitHub API Core

Compact wrapper around the GitHub CLI that normalizes repo metadata, clones templates, fetches file contents, and provisions new repositories.

## Overview
- Ensures the `gh` CLI is installed and authenticated once per process (`require_gh` cache)
- Accepts HTTPS, SSH, and bare `owner/repo` inputs while resolving canonical names + default branches
- Provides repo-scoped helpers for cloning, single-file fetches, and managed temp dirs
- Automates repository creation + initial pushes, including sanitized HTTPS URL generation

## Features
- **Repo helper objects** – `GithubApi.repo(...)` returns a `GithubRepo` with cached metadata & logger context
- **Flexible cloning** – clone into a persistent destination or a managed temp dir with optional callback cleanup
- **Fine-grained file reads** – fetch raw bytes/text for any path via `gh api repos/:owner/:repo/contents/...`
- **Provisioning utilities** – create repos, push initial commits, and compute canonical HTTPS URLs with `build_repo_url`
- **Org + auth helpers** – surface authenticated user login and organization memberships for wizard prompts

## Quickstart

Clone into a temporary directory and process files inline:

```python
from pathlib import Path
from cores.github_api_core.api import GithubApi

api = GithubApi()
repo = api.repo("https://github.com/octocat/Hello-World")

def inspect(clone_dir: str) -> None:
    for entry in sorted(Path(clone_dir).iterdir()):
        print(entry.name)

repo.clone_repo(callback=inspect)
```

Persist the clone and create a repo:

```python
from cores.github_api_core.api import GithubApi

api = GithubApi()
repo = api.repo("github/gitignore")
dest = repo.clone_repo(dest_path="./cache/gitignore", clone_args=["--depth=1"])

api.create_repo(owner="my-org", name="gitignore-fork", private=True)
api.push_initial_commit(dest, owner="my-org", name="gitignore-fork")
```

Fetch a single file as text:

```python
from cores.github_api_core.api import GithubApi

api = GithubApi()
repo = api.repo("github/gitignore", branch="main")
license_text = repo.get_file("LICENSE")
```

## API

```python
class GithubApi:
    def __init__(self, *, temp_mgr: TempFilesManager | None = None, timeout: int = 15) -> None: ...
    def repo(self, url: str, branch: str | None = None) -> GithubRepo: ...
    def create_repo(
        self,
        owner: str,
        name: str,
        *,
        private: bool = False,
        description: str | None = None,
        source: str | None = None,
    ) -> bool: ...
    def get_user_orgs(self) -> list[dict[str, Any]]: ...
    def get_authenticated_user_login(self) -> str: ...
    def push_initial_commit(
        self,
        repo_path: str | pathlib.Path,
        owner: str,
        name: str,
        *,
        branch: str = "main",
        message: str = "init commit",
    ) -> None: ...
    @staticmethod
    def build_repo_url(owner: str, name: str) -> str: ...
    @staticmethod
    def sanitize_repo_name(name: str) -> str: ...
    @classmethod
    def require_gh(cls) -> str: ...

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

## Notes
- Provide either `dest_path` or `callback`; when both are set the callback receives the persistent path.
- `clone_args` defaults to `--depth=1` for fast operations—pass an empty list for full history.
- All gh invocations capture stderr to aid debugging; inspect the logs when an operation returns `False`.

## Requirements & prerequisites
- GitHub CLI (`gh`) installed and authenticated against `github.com`.
- Git ≥ 2.25 available on PATH (provided by `gh` installations on most systems).
- Python dependencies listed in `requirements.txt`: `GitPython`, `requests`.
- Network access to `github.com` and `raw.githubusercontent.com`.

## Troubleshooting
- **`ADHDError` referencing install/login** – run `gh auth status` or reinstall the CLI following the steps in `url_utils.py`.
- **Clone returns `False`** – double-check repository permissions or branch names; stderr is logged alongside the failure.
- **`ValueError` from `_canonical_repo_name`** – the provided URL/slug is invalid or inaccessible; try the full `owner/name` syntax.
- **`Failed to push initial commit`** – ensure the target path is a git repo and you have push rights before rerunning.

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
- Temp Files Manager – manages the directories used for ephemeral clones
- Creator Common Core – shared helpers that rely on GithubApi for cloning/pushing
- Project Creator Core – project scaffolding built on this API
- Module Creator Core – module scaffolding + repo automation
