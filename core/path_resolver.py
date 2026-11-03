"""
Cross-Platform Path Resolver and Workspace Semantic Awareness Engine
Implements industry-standard directory resolution and title sanitization.
"""
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

def sanitize_filename(name: str, max_length: int = 80) -> str:
    r"""
    Purify file/folder names by removing illegal filesystem characters:
    Windows / macOS / Linux disallowed characters: \ / : * ? " < > |
    Also trims extra whitespace and truncates safely.
    """
    if not name:
        return "untitled_asset"
    
    # Replace illegal filesystem characters with underscores
    clean = re.sub(r'[\\/*?:"<>|\r\n\t]', "_", name)
    # Collapse multiple underscores or spaces
    clean = re.sub(r"[\s_]+", "_", clean).strip(" ._-")
    
    if not clean:
        return "untitled_asset"
        
    # Safe truncation preventing cutoffs mid-character
    if len(clean) > max_length:
        clean = clean[:max_length].rstrip(" ._-")
        
    return clean

def get_system_downloads_dir() -> Path:
    """
    Resolve the OS-native default user Downloads directory across:
    - macOS: ~/Downloads
    - Windows: %USERPROFILE%\\Downloads
    - Linux: $XDG_DOWNLOAD_DIR or ~/Downloads
    """
    home = Path.home()
    
    # Linux XDG user dirs support
    if sys.platform.startswith("linux"):
        xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "user-dirs.dirs"
        if xdg_config.exists():
            try:
                with open(xdg_config, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("XDG_DOWNLOAD_DIR="):
                            val = line.split("=", 1)[1].strip().strip('"')
                            val = val.replace("$HOME", str(home))
                            p = Path(val)
                            if p.exists():
                                return p
            except Exception:
                pass

    # Windows & macOS standard
    default_downloads = home / "Downloads"
    if default_downloads.exists():
        return default_downloads

    return home

def detect_workspace_dir() -> Optional[Path]:
    """
    Inspect the current working directory to detect if the user is working
    within a code repository or project workspace, and locate existing
    semantic download/asset folders (e.g. downloads/, data/, assets/, media/).
    """
    cwd = Path.cwd().resolve()
    
    # Look for project markers in cwd or parents (up to 2 levels)
    candidates = [cwd]
    if cwd.parent != cwd:
        candidates.append(cwd.parent)

    search_dirs = ["downloads", "download", "assets", "media", "data", "output", "files"]

    for base in candidates:
        has_project_marker = any((base / marker).exists() for marker in [
            ".git", "pyproject.toml", "package.json", "go.mod", "Cargo.toml", ".gemini"
        ])
        if has_project_marker:
            # Check for existing download-related directory
            for d in search_dirs:
                target = base / d
                if target.is_dir():
                    return target

    return None

def resolve_output_directory(
    explicit_path: Optional[str] = None,
    title: Optional[str] = None,
    create_subfolder: bool = True
) -> Path:
    """
    Hierarchical output directory resolution:
    1. Explicit CLI argument `-o / --output-dir <path>`
    2. Environment variable `DA_OUTPUT_DIR`
    3. Workspace semantic directory (e.g. `./downloads` if running inside a project)
    4. OS Native Downloads folder (`~/Downloads/DownloadAnything`)
    """
    # 1. Explicit path
    if explicit_path:
        base = Path(os.path.expanduser(explicit_path)).resolve()
    else:
        # 2. Environment variable
        env_dir = os.environ.get("DA_OUTPUT_DIR")
        if env_dir and env_dir.strip():
            base = Path(os.path.expanduser(env_dir.strip())).resolve()
        else:
            # 3. Workspace semantic awareness
            workspace_dir = detect_workspace_dir()
            if workspace_dir:
                base = workspace_dir
            else:
                # 4. OS native Downloads fallback
                base = get_system_downloads_dir() / "DownloadAnything"

    # Create subfolder per asset: [YYYY-MM-DD]_[clean_title]
    if create_subfolder and title:
        date_prefix = datetime.now().strftime("%Y-%m-%d")
        clean_title = sanitize_filename(title, max_length=60)
        folder_name = f"{date_prefix}_{clean_title}"
        base = base / folder_name

    return base
