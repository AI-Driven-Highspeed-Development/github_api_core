# GitHub API Core

Small, dependency‑light helper for working with GitHub repositories. It supports both:
- Entire repository clone (over SSH or HTTPS)
- Single-file retrieval without cloning the whole repo

No GitHub CLI is required. For HTTPS access to private files, you can provide a token (or set `GITHUB_TOKEN`). For SSH, standard git/ssh configuration is used.

## Overview
- Accepts repo references in SSH, HTTPS, or `owner/repo` form
- Precomputes normalized forms: `ssh_url`, `https_url`, and `repo_full_name`
- Chooses protocol automatically based on the input URL
- Uses a temporary working directory for git operations and cleans it up on request

## Features
- Full clone
	- SSH input → clone via SSH
	- HTTPS input → clone via HTTPS (uses your git credential helper if needed)
- Single-file fetch
	- SSH input → shallow sparse-checkout via git (no token required)
	- HTTPS input → `raw.githubusercontent.com` (adds `Authorization` if a token is provided)
- Minimal configuration; works with public repos out of the box
- Optional token support via constructor or `GITHUB_TOKEN` environment variable

## Quickstart

Public single file over HTTPS (no token required):

```python
from cores.github_api_core import GithubApi

api = GithubApi("https://github.com/github/gitignore", branch="main")
text = api.get_file("Python.gitignore")
print(text[:200])
```

Single file over SSH (no token required):

```python
from cores.github_api_core import GithubApi

api = GithubApi("git@github.com:github/gitignore.git", branch="main")
text = api.get_file("Python.gitignore")
```

Clone a repository (public HTTPS):

```python
from cores.github_api_core import GithubApi

api = GithubApi("https://github.com/octocat/Hello-World", branch="main")
dest = api.pull_repo()
# ... use the repo at `dest` ...
api.cleanup_temp(dest)  # remove when done
```

Private single file over HTTPS (requires token):

```python
import os
from cores.github_api_core import GithubApi

os.environ["GITHUB_TOKEN"] = "<your_token>"  # or pass token=...
api = GithubApi("https://github.com/OWNER/PRIVATE_REPO", branch="main")
text = api.get_file("path/to/secret.txt")
```

## API

```python
class GithubApi:
		def __init__(self, url: str, branch: str | None = None, token: str | None = None, temp_mgr: TempFilesManager | None = None, timeout: int = 15) -> None: ...

		# normalized forms computed at init
		ssh_url: str               # git@host:owner/repo.git
		https_url: str             # https://host/owner/repo.git
		repo_full_name: str | None # owner/repo

		def pull_repo(self, dest_path: str | None = None) -> str | bool: ...
		def get_file(self, relative_path: str, *, encoding: str = "utf-8") -> str | None: ...
		def get_file_bytes(self, relative_path: str) -> bytes | None: ...
		def cleanup_temp(self, path: str) -> None: ...
```

Notes
- For HTTPS private content, an access token is required. Provide it via `token=` or `GITHUB_TOKEN`.
- For SSH operations, ensure your git/ssh is configured to access the repo (agent optional if key files are readable by ssh).
- Temporary directories are created for you and can be removed via `cleanup_temp`.

## URL normalization rules
- Input forms accepted:
	- SSH: `git@github.com:owner/repo(.git)` or `ssh://git@github.com/owner/repo(.git)`
	- HTTPS: `https://github.com/owner/repo(.git)`
	- Bare: `owner/repo`
- Normalization produces:
	- `ssh_url` → `git@host:owner/repo.git`
	- `https_url` → `https://host/owner/repo.git`
	- `repo_full_name` → `owner/repo`

## Requirements & prerequisites
- Git ≥ 2.25 (required for `git sparse-checkout --no-cone` used in single-file SSH fetch)
- Python dependencies: `GitPython`, `requests`
- Network access to `github.com` and `raw.githubusercontent.com`

## Troubleshooting
- Private HTTPS single-file returns `None`:
	- Provide a valid token (fine-grained or classic) with sufficient scope; set `GITHUB_TOKEN` or pass `token=`.
- SSH single-file or clone fails:
	- Verify SSH connectivity: `git ls-remote git@github.com:owner/repo.git HEAD`
	- Ensure your SSH key has access and is picked up by ssh (agent or file-based auth)
- Temporary directory not removed:
	- Call `cleanup_temp(dest)` explicitly; or remove manually if needed

## Module structure

```
cores/github_api_core/
├─ __init__.py        # exports GithubApi
├─ api.py             # public API class
├─ url_utils.py       # URL normalization and helpers
├─ fetch_https.py     # Raw file fetch over HTTPS
├─ fetch_ssh.py       # Clone + sparse-checkout for SSH
├─ requirements.txt   # module-specific deps (GitPython)
└─ README.md          # this file
```

## See also
- YAML Reading Core: parse, validate, and save YAML content fetched from repos
- Temp Files Manager: centralized temp directory creation and cleanup used by clone/fetch
