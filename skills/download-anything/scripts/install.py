#!/usr/bin/env python3
"""Install the bundled wheel (or this source checkout) using only Python stdlib."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", type=Path, default=Path.home() / ".download-anything" / "venv")
    args = parser.parse_args()
    skill_dir = Path(__file__).resolve().parents[1]
    wheels = sorted((skill_dir / "assets").glob("download_anything-*.whl"))
    source = skill_dir.parent.parent
    if wheels:
        package = str(wheels[-1])
    elif (source / "pyproject.toml").is_file() and (source / "cli.py").is_file():
        package = str(source)
    else:
        parser.error("No bundled CLI wheel found. Obtain the complete Skill release ZIP or a source checkout.")
    target = args.venv.expanduser().resolve()
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    uv = shutil.which("uv")
    if uv:
        if not python.is_file():
            if sys.version_info >= (3, 10):
                subprocess.run([uv, "venv", "--python", sys.executable, str(target)], check=True)
            else:
                # The running interpreter is too old for the bundled wheel; let uv pick a suitable one.
                subprocess.run([uv, "venv", str(target)], check=True)
        command = [uv, "pip", "install", "--python", str(python), package]
    else:
        if sys.version_info < (3, 10):
            sys.exit("Download Anything requires Python >= 3.10. "
                     "Install uv (recommended) or a newer Python, then retry.")
        venv.EnvBuilder(with_pip=True).create(target)
        command = [str(python), "-m", "pip", "install", package]
    subprocess.run(command, check=True)
    executable = target / ("Scripts/da.exe" if os.name == "nt" else "bin/da")
    subprocess.run([str(executable), "--help"], check=True, stdout=subprocess.DEVNULL)
    print(f"Installed: {executable}")
    print("Add its parent directory to PATH, or invoke the full path above.")


if __name__ == "__main__":
    main()
