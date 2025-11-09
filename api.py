from __future__ import annotations

import shutil
import subprocess
import json
from pathlib import Path
from typing import Any, Callable, Optional

from managers.temp_files_manager.temp_files_manager import TempFilesManager
from utils.logger_util.logger import Logger

from .url_utils import GH_INSTALL_GUIDE, GH_LOGIN_GUIDE

class GithubApi:
    """GitHub CLI helper providing repo-agnostic operations."""

    def __init__(
        self,
        *,
        token: Optional[str] = None,
        temp_mgr: Optional[TempFilesManager] = None,
        timeout: int = 15,
    ) -> None:
        self.logger = Logger(name=self.__class__.__name__)
        self.token = token
        self.timeout = timeout
        self._gh_path = self.require_gh()
        self.temp_mgr = temp_mgr or TempFilesManager()

    def repo(self, url: str, branch: Optional[str] = None) -> "GithubRepo":
        """Create a repo-scoped helper bound to the provided URL."""
        return GithubRepo(api=self, url=url, branch=branch)

    # ---------------- Public methods ----------------
    def create_repo(
        self,
        name_with_owner: str,
        *,
        private: bool = False,
        description: Optional[str] = None,
        source: Optional[str] = None,
    ) -> bool:
        """Create a new repository via GitHub CLI."""
        if not name_with_owner or "/" not in name_with_owner:
            raise ValueError("name_with_owner must be in the form 'owner/repo'")

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
            raise RuntimeError(
                "Failed to resolve authenticated user login: "
                f"{result.stderr.decode('utf-8', errors='replace').strip()}"
            )

        login = result.stdout.decode("utf-8", errors="replace").strip()
        if not login:
            raise RuntimeError("GitHub CLI did not return an authenticated user login.")
        return login

    def push_initial_commit(
        self,
        repo_path: str | Path,
        name_with_owner: str,
        *,
        branch: str = "main",
        message: str = "init commit",
    ) -> None:
        """Initialize a git repo at repo_path and push the first commit to GitHub."""

        target = Path(repo_path).expanduser().resolve()
        if not target.is_dir():
            raise ValueError(f"repo_path must be a directory: {repo_path}")

        remote_url = f"https://github.com/{name_with_owner}.git"

        # Initialize repository and create initial commit
        init_result = self._run_git(["init"], cwd=target, check=False)
        if init_result.returncode != 0:
            raise RuntimeError(
                f"Failed to initialize git repository: {init_result.stderr.decode('utf-8', errors='replace').strip()}"
            )

        add_result = self._run_git(["add", "--all"], cwd=target, check=False)
        if add_result.returncode != 0:
            raise RuntimeError(
                f"Failed to stage project files: {add_result.stderr.decode('utf-8', errors='replace').strip()}"
            )

        commit_result = self._run_git(["commit", "-m", message], cwd=target, check=False)
        if commit_result.returncode != 0:
            detail = commit_result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Failed to create initial commit: {detail}")

        branch_result = self._run_git(["branch", "-M", branch], cwd=target, check=False)
        if branch_result.returncode != 0:
            detail = branch_result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Failed to set branch to {branch}: {detail}")

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
                raise RuntimeError(f"Failed to configure remote origin: {detail}")

        push_result = self._run_git(["push", "-u", "origin", branch], cwd=target, check=False)
        if push_result.returncode != 0:
            detail = push_result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Failed to push initial commit: {detail}")

    # ---------------- Static methods ----------------
    @staticmethod
    def require_gh() -> str:
        gh_path = shutil.which("gh")
        if not gh_path:
            raise RuntimeError(GH_INSTALL_GUIDE)
        version = subprocess.run([gh_path, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if version.returncode != 0:
            raise RuntimeError(GH_INSTALL_GUIDE)
        status = subprocess.run(
            [gh_path, "auth", "status", "--hostname", "github.com"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if status.returncode != 0:
            detail = status.stderr.decode("utf-8", errors="replace").strip()
            message = f"{detail}\n\n{GH_LOGIN_GUIDE}" if detail else GH_LOGIN_GUIDE
            raise RuntimeError(message)
        return gh_path

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
            raise RuntimeError(f"Git command failed ({' '.join(cmd)}): {detail}")
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
        cmd = [
            self.api._gh_path,
            "api",
            f"repos/{self.repo_full_name}/contents/{clean_path}",
            "-H",
            "Accept: application/vnd.github.raw",
        ]
        if self.branch:
            cmd.extend(["-f", f"ref={self.branch}"])
        result = self.api._run(cmd)
        if result.returncode == 0:
            return result.stdout
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

