from __future__ import annotations

import os
import subprocess
from typing import Optional

from git import Repo
from utils.logger_util.logger import Logger
from managers.temp_files_manager.temp_files_manager import TempFilesManager

logger = Logger(name="GithubFetchSSH")

def clone_repo(repo_url: str, dest_path: str) -> bool:
    try:
        Repo.clone_from(repo_url, dest_path)
        return True
    except Exception as e:
        logger.error(f"Error cloning repository: {e}")
        return False


def fetch_file_sparse(
    ssh_url: str,
    branch: str,
    relative_path: str,
    *,
    temp_mgr: TempFilesManager
) -> Optional[bytes]:
    """Use shallow sparse-checkout over SSH to fetch a single file without a PAT."""
    temp_dir = temp_mgr.make_dir(prefix="git")
    try:
        subprocess.run(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                "--depth=1",
                "--branch",
                branch,
                ssh_url,
                temp_dir,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(["git", "sparse-checkout", "init", "--no-cone"], check=True, cwd=temp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "sparse-checkout", "set", relative_path], check=True, cwd=temp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "checkout"], check=True, cwd=temp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        target = os.path.join(temp_dir, relative_path)
        with open(target, "rb") as f:
            return f.read()
    except subprocess.CalledProcessError as e:
        msg = e.stderr.decode("utf-8", errors="replace") if e.stderr else str(e)
        logger.error(f"sparse-checkout failed: {msg}")
        return None
    except Exception as e:
        logger.error(f"Error reading sparse-checkout file: {e}")
        return None
    finally:
        temp_mgr.cleanup(temp_dir)
