from __future__ import annotations

import base64
import shutil
import subprocess
import json
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

from temp_files_manager import TempFilesManager
from logger_util import Logger
from exceptions_core import ADHDError

from .url_utils import GH_INSTALL_GUIDE, GH_LOGIN_GUIDE

class GithubApi:
    """GitHub CLI helper providing repo-agnostic operations."""

    # Cached path to the GitHub CLI; resolved once per process
    _GH_PATH: Optional[str] = None

    def __init__(
        self,
        *,
        temp_mgr: Optional[TempFilesManager] = None,
        timeout: int = 15,
    ) -> None:
        self.logger = Logger(name=self.__class__.__name__)
        self.timeout = timeout
        self.temp_mgr = temp_mgr or TempFilesManager()

    def repo(self, url: str, branch: Optional[str] = None) -> "GithubRepo":
        """Create a repo-scoped helper bound to the provided URL."""
        return GithubRepo(api=self, url=url, branch=branch)

    # ---------------- Public methods ----------------
    def create_repo(
        self,
        owner: str,
        name: str,
        *,
        private: bool = False,
        description: Optional[str] = None,
        source: Optional[str] = None,
    ) -> bool:
        """Create a new repository via GitHub CLI."""
        if not owner or not name:
            raise ValueError("owner and name must be non-empty")

        name_with_owner = f"{owner}/{name}"

        cmd = [
            self._gh_path,
            "repo",
            "create",
            name_with_owner,
            "--public" if not private else "--private",
            "--confirm",
        ]

        if source:
            cmd.extend(["--source", source])

        if description:
            cmd.extend(["--description", description])

        result = self._run(cmd)
        if result.returncode != 0:
            self.logger.error(
                f"Failed to create {name_with_owner}: "
                f"{result.stderr.decode('utf-8', errors='replace').strip()}"
            )
            return False
        self.logger.info(f"Created repository {name_with_owner}.")
        return True

    def get_user_orgs(self) -> list[dict[str, Any]]:
        """Return the authenticated user's organizations as dictionaries."""
        cmd = [
            self._gh_path,
            "api",
            "user/orgs",
            "--paginate",
            "--jq",
            ".[]",
        ]
        result = self._run(cmd)
        if result.returncode != 0:
            self.logger.error(
                "Failed to fetch user organizations: "
                f"{result.stderr.decode('utf-8', errors='replace').strip()}"
            )
            return []

        payload = result.stdout.decode("utf-8", errors="replace").strip()
        if not payload:
            return []

        orgs: list[dict[str, Any]] = []
        for line in payload.splitlines():
            clean = line.strip()
            if not clean:
                continue
            try:
                orgs.append(json.loads(clean))
            except json.JSONDecodeError as exc:
                self.logger.error(f"Failed to parse organization entry: {exc}")
                return []
        return orgs

    def get_authenticated_user_login(self) -> str:
        """Return the login of the authenticated user."""
        cmd = [self._gh_path, "api", "user", "--jq", ".login"]
        result = self._run(cmd)
        if result.returncode != 0:
            raise ADHDError(
                "Failed to resolve authenticated user login: "
                f"{result.stderr.decode('utf-8', errors='replace').strip()}"
            )

        login = result.stdout.decode("utf-8", errors="replace").strip()
        if not login:
            raise ADHDError("GitHub CLI did not return an authenticated user login.")
        return login

    def push_initial_commit(
        self,
        repo_path: str | Path,
        owner: str,
        name: str,
        *,
        branch: str = "main",
        message: str = "init commit",
    ) -> None:
        """Initialize a git repo at repo_path and push the first commit to GitHub."""

        target = Path(repo_path).expanduser().resolve()
        if not target.is_dir():
            raise ValueError(f"repo_path must be a directory: {repo_path}")
        # Build canonical HTTPS URL from owner and name
        remote_url = self.build_repo_url(owner, name)

        # Initialize repository and create initial commit
        init_result = self._run_git(["init"], cwd=target, check=False)
        if init_result.returncode != 0:
            raise ADHDError(
                f"Failed to initialize git repository: {init_result.stderr.decode('utf-8', errors='replace').strip()}"
            )

        add_result = self._run_git(["add", "--all"], cwd=target, check=False)
        if add_result.returncode != 0:
            raise ADHDError(
                f"Failed to stage project files: {add_result.stderr.decode('utf-8', errors='replace').strip()}"
            )

        commit_result = self._run_git(["commit", "-m", message], cwd=target, check=False)
        if commit_result.returncode != 0:
            detail = commit_result.stderr.decode("utf-8", errors="replace").strip()
            raise ADHDError(f"Failed to create initial commit: {detail}")

        branch_result = self._run_git(["branch", "-M", branch], cwd=target, check=False)
        if branch_result.returncode != 0:
            detail = branch_result.stderr.decode("utf-8", errors="replace").strip()
            raise ADHDError(f"Failed to set branch to {branch}: {detail}")

        remote_add = self._run_git(["remote", "add", "origin", remote_url], cwd=target, check=False)
        if remote_add.returncode != 0:
            # Attempt to update the remote if it already exists
            remote_set = self._run_git(
                ["remote", "set-url", "origin", remote_url], cwd=target, check=False
            )
            if remote_set.returncode != 0:
                detail = remote_set.stderr.decode("utf-8", errors="replace").strip()
                if not detail:
                    detail = remote_add.stderr.decode("utf-8", errors="replace").strip()
                raise ADHDError(f"Failed to configure remote origin: {detail}")

        push_result = self._run_git(["push", "-u", "origin", branch], cwd=target, check=False)
        if push_result.returncode != 0:
            detail = push_result.stderr.decode("utf-8", errors="replace").strip()
            raise ADHDError(f"Failed to push initial commit: {detail}")

    # ---------------- Convenience helpers ----------------
    @staticmethod
    def build_repo_url(owner: str, name: str) -> str:
        """Return a canonical https GitHub repo URL for the given owner/name.

        Spaces are converted to dashes to mirror gh repo create semantics.
        """
        sanitized_repo_name = GithubApi.sanitize_repo_name(name)
        if not owner or not sanitized_repo_name:
            raise ValueError("owner and name must be non-empty to build repo URL")
        return f"https://github.com/{owner}/{sanitized_repo_name}.git"
    
    @staticmethod
    def sanitize_repo_name(name: str) -> str:
        """Sanitize a repository name by stripping whitespace and replacing spaces with dashes."""
        sanitized_repo_name = name.strip().replace(" ", "-")
        return sanitized_repo_name

    # ---------------- Static methods ----------------
    @classmethod
    def require_gh(cls) -> str:
        """Resolve and validate the GitHub CLI path once, caching the result."""
        if cls._GH_PATH:
            return cls._GH_PATH
        gh_path = shutil.which("gh")
        if not gh_path:
            raise ADHDError(GH_INSTALL_GUIDE)
        version = subprocess.run([gh_path, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if version.returncode != 0:
            raise ADHDError(GH_INSTALL_GUIDE)
        status = subprocess.run(
            [gh_path, "auth", "status", "--hostname", "github.com"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if status.returncode != 0:
            detail = status.stderr.decode("utf-8", errors="replace").strip()
            message = f"{detail}\n\n{GH_LOGIN_GUIDE}" if detail else GH_LOGIN_GUIDE
            raise ADHDError(message)
        cls._GH_PATH = gh_path
        return gh_path

    @property
    def _gh_path(self) -> str:
        """Expose the cached GH path via an instance property without re-checking."""
        return self.__class__.require_gh()

    # ---------------- Internal helpers ----------------
    def _run(self, cmd: list[str]) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=self.timeout,
        )

    def _run_git(
        self,
        args: list[str],
        *,
        cwd: Path,
        check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        cmd = ["git", *args]
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=self.timeout,
        )
        if check and result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise ADHDError(f"Git command failed ({' '.join(cmd)}): {detail}")
        return result


class GithubRepo:
    """Repository-scoped helper built on top of GithubApi."""

    def __init__(self, api: GithubApi, *, url: str, branch: Optional[str] = None) -> None:
        clean_url = url.strip()
        if not clean_url:
            raise ValueError("url must not be empty")

        self.api = api
        self.url = clean_url
        metadata = self._resolve_repo_metadata(self.api, self.url, branch)
        self.repo_full_name = metadata["name_with_owner"]
        self.branch = metadata["branch"]
        self.owner, self.repo_name = self._split_name_with_owner(self.repo_full_name)
        self.logger = Logger(name=f"{self.__class__.__name__}:{self.repo_full_name}")
        self.logger.debug(
            f"Initialized GithubRepo for repo {self.repo_full_name} on branch {self.branch}."
        )

    def clone_repo(
        self,
        dest_path: Optional[str] = None,
        *,
        callback: Optional[Callable[[str], Any]] = None,
        clone_args: Optional[list[str]] = None,
    ) -> Any:
        """Clone the repository via GitHub CLI."""
        if dest_path is None and callback is None:
            raise ValueError("clone_repo requires dest_path or callback to be supplied.")

        created_temp = dest_path is None
        target = dest_path or self.api.temp_mgr.make_dir(prefix="clone")
        clone_args = clone_args or ["--depth=1"]

        branch = self.branch
        if branch:
            clone_args.extend(["--branch", branch])
        cmd = [
            self.api._gh_path,
            "repo",
            "clone",
            self.repo_full_name,
            target,
            "--",
            *clone_args,
        ]
        result = self.api._run(cmd)
        if result.returncode == 0:
            if callback:
                try:
                    return callback(target)
                finally:
                    if created_temp:
                        self.api.temp_mgr.cleanup(target)
            return target
        self.logger.error(
            f"Failed to clone {self.repo_full_name}: {result.stderr.decode('utf-8', errors='replace').strip()}"
        )
        if created_temp:
            self.api.temp_mgr.cleanup(target)
        return False

    def get_file(self, relative_path: str, *, encoding: str = "utf-8") -> Optional[str]:
        """Fetch a single file and return its decoded text."""
        data = self.get_file_bytes(relative_path)
        if data is None:
            return None
        try:
            return data.decode(encoding, errors="replace")
        except Exception:
            return data.decode("utf-8", errors="replace")

    def get_file_bytes(self, relative_path: str) -> Optional[bytes]:
        """Fetch a single file via gh api."""
        clean_path = relative_path.strip().lstrip("/")
        if not clean_path:
            raise ValueError("relative_path must not be empty")
        url = f"repos/{self.repo_full_name}/contents/{clean_path}"
        if self.branch:
            url = url + f"?ref={self.branch}"
        cmd = [
            self.api._gh_path,
            "api",
            url
        ]
        result = self.api._run(cmd)
        if result.returncode == 0:
            output = result.stdout
            if not output:
                self.logger.error(f"File {clean_path} is empty.")
                return b""
            try:
                payload = json.loads(output.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                self.logger.error(f"Failed to decode JSON for {clean_path}.")
                return output

            if isinstance(payload, dict):
                content = payload.get("content")
                encoding = payload.get("encoding")
                if isinstance(content, str):
                    normalized = content.strip().encode()
                    if encoding == "base64":
                        try:
                            return base64.b64decode(normalized)
                        except Exception as exc:
                            self.logger.error(
                                f"Failed to decode base64 content for {clean_path}: {exc}"
                            )
                            return None
                    return normalized
            return output
        self.logger.error(
            f"Failed to fetch {clean_path}: {result.stderr.decode('utf-8', errors='replace').strip()}"
        )
        return None

    def cleanup_temp(self, path: str) -> None:
        self.api.temp_mgr.cleanup(path)

    @staticmethod
    def _resolve_repo_metadata(
        api: GithubApi, url: str, branch_override: Optional[str]
    ) -> dict[str, Optional[str]]:
        if branch_override:
            return {
                "name_with_owner": GithubRepo._canonical_repo_name(api, url),
                "branch": branch_override,
            }

        cmd = [
            api._gh_path,
            "repo",
            "view",
            url,
            "--json",
            "nameWithOwner,defaultBranchRef",
            "--jq",
            "{name_with_owner: .nameWithOwner, branch: .defaultBranchRef.name}",
        ]
        result = api._run(cmd)
        if result.returncode != 0 or not result.stdout:
            api.logger.debug(
                "Using fallback canonical name; gh repo view failed to return metadata."
            )
            return {
                "name_with_owner": GithubRepo._canonical_repo_name(api, url),
                "branch": branch_override,
            }

        try:
            parsed: dict[str, Optional[str]] = json.loads(result.stdout.decode("utf-8"))
            if not parsed.get("name_with_owner"):
                parsed["name_with_owner"] = GithubRepo._canonical_repo_name(api, url)
            if branch_override:
                parsed["branch"] = branch_override
            return parsed
        except Exception as exc:
            api.logger.debug(f"Failed to parse gh repo view output: {exc}")
            return {
                "name_with_owner": GithubRepo._canonical_repo_name(api, url),
                "branch": branch_override,
            }

    @staticmethod
    def _canonical_repo_name(api: GithubApi, url: str) -> str:
        cmd = [
            api._gh_path,
            "repo",
            "view",
            url,
            "--json",
            "nameWithOwner",
            "--jq",
            ".nameWithOwner",
        ]
        result = api._run(cmd)
        if result.returncode == 0:
            name = result.stdout.decode("utf-8", errors="replace").strip()
            if name:
                return name
        raise ValueError("Unable to determine canonical repository name from GitHub CLI.")

    @staticmethod
    def _split_name_with_owner(value: str) -> Tuple[str, str]:
        if not value or "/" not in value:
            raise ValueError("Repository full name must be in 'owner/name' format.")
        owner, repo_name = value.split("/", 1)
        owner = owner.strip()
        repo_name = repo_name.strip()
        if not owner or not repo_name:
            raise ValueError("Repository owner and name must be non-empty.")
        return owner, repo_name

