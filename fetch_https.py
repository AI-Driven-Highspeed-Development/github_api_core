from __future__ import annotations

from typing import Optional
import requests


def fetch_raw_file(owner_repo: str, branch: str, relative_path: str, *, token: Optional[str] = None, timeout: int = 15) -> Optional[bytes]:
    """Fetch a single file via raw.githubusercontent.com.
    If token is provided, sends Authorization header (required for private repos).
    """
    raw_url = f"https://raw.githubusercontent.com/{owner_repo}/{branch}/{relative_path}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(raw_url, headers=headers, timeout=timeout)
    if resp.status_code == 200:
        return resp.content
    return None
