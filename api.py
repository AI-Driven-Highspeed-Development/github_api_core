from __future__ import annotations

import os
from typing import Optional

from managers.config_manager import ConfigManager
from managers.temp_files_manager.temp_files_manager import TempFilesManager
from utils.logger_util.logger import Logger

from .url_utils import (
    is_ssh_url,
    to_ssh_url,
    to_https_url,
    https_repo_full_name,
)
from .fetch_https import fetch_raw_file
from .fetch_ssh import clone_repo, fetch_file_sparse


class GithubApi:
    """High-level GitHub API for cloning repos and fetching single files.
    Assumes no GitHub CLI. Uses SSH for git ops when URL is SSH; otherwise HTTPS.
    """

    def __init__(
        self,
        url: str,
        branch: Optional[str] = None,
        token: Optional[str] = None,
        temp_mgr: Optional[TempFilesManager] = None,
        timeout: int = 15,
    ) -> None:
        self.logger = Logger(name=self.__class__.__name__)
        self.cm = ConfigManager()

        self.url = url.strip()
        self.branch = branch or "main"
        # Prefer explicit token, else env; only used for HTTPS raw/API
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.timeout = timeout

        # Precompute normalized forms
        self.ssh_url = to_ssh_url(self.url)
        self.https_url = to_https_url(self.url)
        self.repo_full_name = https_repo_full_name(self.url)  # owner/repo

        # Temp manager (use temp_files_manager module for temp paths)
        self.temp_mgr = temp_mgr or TempFilesManager()

    # ---------------- Public methods ----------------
    def pull_repo(self, dest_path: Optional[str] = None) -> str | bool:
        """Clone the repository to dest_path.
        Returns dest_path on success, False on failure.
        """
        if not dest_path:
            dest_path = self.temp_mgr.make_dir(prefix="clone")
        repo_url = self.ssh_url if is_ssh_url(self.url) else self.https_url
        ok = clone_repo(repo_url, dest_path, logger=self.logger)
        return dest_path if ok else False

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
        """Fetch a single file and return its bytes.
        SSH URL -> sparse checkout via git (no token).
        HTTPS URL -> raw.githubusercontent.com (token if provided).
        """
        if is_ssh_url(self.url):
            return fetch_file_sparse(self.ssh_url, self.branch, relative_path, temp_mgr=self.temp_mgr, logger=self.logger)

        # HTTPS path: requires token for private repos; public works without
        if not self.repo_full_name:
            self.logger.error("Unable to derive owner/repo from URL")
            return None
        return fetch_raw_file(self.repo_full_name, self.branch, relative_path, token=self.token, timeout=self.timeout)

    def cleanup_temp(self, path: str) -> None:
        self.temp_mgr.cleanup(path)
