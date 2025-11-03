from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse


def strip_git_suffix(url: str) -> str:
    """Return url without a trailing .git, if present (safe literal check)."""
    return url[:-4] if url.endswith(".git") else url


def ensure_git_suffix(url: str) -> str:
    """Ensure the URL ends with exactly one .git suffix (safe literal add)."""
    u = strip_git_suffix(url)
    return f"{u}.git"


def is_ssh_url(repo_url: str) -> bool:
    if repo_url.startswith("git@"):
        return True
    parsed = urlparse(repo_url)
    return parsed.scheme == "ssh"


def to_ssh_url(repo_url: str) -> str:
    """Convert a given repo reference to SSH form git@host:owner/repo.git.
    Accepts HTTPS URL, SSH URL, or bare owner/repo.
    """
    if is_ssh_url(repo_url):
        # Normalize ssh://git@host/owner/repo(.git) -> git@host:owner/repo.git
        if repo_url.startswith("git@"):
            return ensure_git_suffix(repo_url)
        parsed = urlparse(repo_url)
        host = parsed.hostname or parsed.netloc
        owner_repo = strip_git_suffix(parsed.path.lstrip("/"))
        return f"git@{host}:{owner_repo}.git"

    # git@host:path case handled above; handle https or bare
    parsed = urlparse(repo_url)
    if parsed.netloc and parsed.path:
        host = parsed.netloc
        owner_repo = strip_git_suffix(parsed.path.lstrip("/"))
        return f"git@{host}:{owner_repo}.git"

    # Bare owner/repo
    owner_repo = strip_git_suffix(repo_url.strip().lstrip("/"))
    if "/" in owner_repo:
        return f"git@github.com:{owner_repo}.git"
    # If the input doesn't look like owner/repo, just enforce suffix
    return ensure_git_suffix(repo_url)


def to_https_url(repo_url: str) -> str:
    """Convert a given repo reference to HTTPS form https://host/owner/repo.git.
    Accepts SSH URL, HTTPS URL, or bare owner/repo.
    """
    if not is_ssh_url(repo_url):
        # Already http(s) or bare
        parsed = urlparse(repo_url)
        if parsed.netloc and parsed.scheme in {"http", "https"}:
            return ensure_git_suffix(repo_url)
        # Bare owner/repo
        owner_repo = strip_git_suffix(repo_url.strip().lstrip("/"))
        if "/" in owner_repo:
            return f"https://github.com/{owner_repo}.git"
        return ensure_git_suffix(repo_url)

    # Convert git@host:path or ssh:// to https
    if repo_url.startswith("git@"):
        host_path = repo_url.split(":", 1)
        if len(host_path) == 2:
            host = host_path[0].replace("git@", "")
            owner_repo = strip_git_suffix(host_path[1])
            return f"https://{host}/{owner_repo}.git"
        return ensure_git_suffix(repo_url)

    parsed = urlparse(repo_url)
    if parsed.netloc and parsed.path:
        # Handle ssh:// form where netloc may include user@host
        host = parsed.hostname or parsed.netloc
        owner_repo = strip_git_suffix(parsed.path.lstrip("/"))
        return f"https://{host}/{owner_repo}.git"

    return ensure_git_suffix(repo_url)


def https_repo_full_name(repo_url: str) -> Optional[str]:
    """Return owner/repo for any supported input (ssh, https, or bare)."""
    u = repo_url.strip()

    if u.startswith("git@"):
        # git@host:owner/repo(.git)
        try:
            _, path = u.split(":", 1)
            return strip_git_suffix(path).strip("/") or None
        except ValueError:
            return None

    parsed = urlparse(u)
    if parsed.netloc and parsed.path:
        # https://host/owner/repo(.git) or ssh://git@host/owner/repo(.git)
        return strip_git_suffix(parsed.path.strip("/")) or None

    # Bare owner/repo
    return strip_git_suffix(u.strip("/")) or None
