import os
import sys

# Add path handling to work from the new nested directory structure
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.getcwd()  # Use current working directory as project root
sys.path.insert(0, project_root)

from cores.github_api_core.api import GithubApi, GithubRepo

__all__ = ["GithubApi", "GithubRepo"]

