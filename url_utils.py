from __future__ import annotations

GH_INSTALL_GUIDE = (
    "GitHub CLI (gh) is required for repository access.\n"
    "Install instructions: https://cli.github.com/\n"
    "Linux command (Ubuntu/Debian): " 
    "sudo apt install gh\n"
    "Arch Linux: "
    "sudo pacman -S github-cli"
)


GH_LOGIN_GUIDE = (
    "GitHub CLI authentication is required.\n"
    "Command to copy: \n"
    "gh auth login --hostname github.com --git-protocol https --web\n"
    "Then run:\n"
    "gh auth status"
)
__all__ = ["GH_INSTALL_GUIDE", "GH_LOGIN_GUIDE"]
