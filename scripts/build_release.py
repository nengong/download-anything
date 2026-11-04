#!/usr/bin/env python3
"""Build a CLI wheel and a self-contained Skill ZIP; never upload anything."""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M)[1]
    uv = shutil.which("uv")
    if uv:
        command = [uv, "build", "--wheel", "--out-dir", str(output)]
    else:
        command = [sys.executable, "-m", "pip", "wheel", "--no-deps", str(ROOT), "--wheel-dir", str(output)]
    subprocess.run(command, cwd=ROOT, check=True)
    wheel = output / f"download_anything-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel) as built:
        if "cli.py" not in built.namelist():
            raise RuntimeError("Built wheel is missing its CLI entrypoint")
    archive = output / f"download-anything-{version}.skill.zip"
    skill = ROOT / "skills" / "download-anything"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(skill / "SKILL.md", "download-anything/SKILL.md")
        for folder in ("references", "scripts"):
            for path in sorted((skill / folder).rglob("*")):
                if path.is_file() and path.suffix in {".md", ".py"} and "__pycache__" not in path.parts:
                    bundle.write(path, "download-anything/" + str(path.relative_to(skill)))
        bundle.write(wheel, f"download-anything/assets/{wheel.name}")
        bundle.write(ROOT / "LICENSE", "download-anything/assets/LICENSE")
    print(archive)


if __name__ == "__main__":
    main()
