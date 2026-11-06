#!/usr/bin/env python3
"""Build a CLI wheel and a self-contained Skill ZIP; never upload anything."""
import base64
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def _record_entry(arcname: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
    return f"{arcname},sha256={digest},{len(data)}"


def _build_wheel_stdlib(wheel_path: Path, version: str) -> None:
    """Offline PEP 427 pure-Python wheel builder using only Python stdlib."""
    dist_info = f"download_anything-{version}.dist-info"
    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    metadata = (
        "Metadata-Version: 2.5\n"
        "Name: download-anything\n"
        f"Version: {version}\n"
        "Summary: High-density micro-asset (<500MB) extraction and offline archiving hub\n"
        "Author: Download Anything Contributors\n"
        "License: MIT\n"
        "License-File: LICENSE\n"
        "Requires-Python: >=3.10\n"
        "Requires-Dist: beautifulsoup4>=4.12.3\n"
        "Requires-Dist: click>=8.1.7\n"
        "Requires-Dist: cryptography>=42.0.0\n"
        "Requires-Dist: gallery-dl>=1.32.19\n"
        "Requires-Dist: pillow>=10.3.0\n"
        "Requires-Dist: pypdf>=4.2.0\n"
        "Requires-Dist: pyyaml>=6.0.1\n"
        "Requires-Dist: requests>=2.31.0\n"
        "Requires-Dist: rich>=13.7.1\n"
        "Requires-Dist: yt-dlp>=2024.0.0\n"
        "Provides-Extra: browser\n"
        "Requires-Dist: rookiepy>=0.4.0; (python_version < '3.13') and extra == 'browser'\n"
        "Provides-Extra: dev\n"
        "Requires-Dist: pytest-mock>=3.14.0; extra == 'dev'\n"
        "Requires-Dist: pytest>=8.2.0; extra == 'dev'\n"
        "Description-Content-Type: text/markdown\n\n"
        f"{readme_text}"
    ).encode("utf-8")
    wheel_meta = (
        "Wheel-Version: 1.0\n"
        "Generator: hatchling 1.33.0\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    ).encode("utf-8")
    entry_points = b"[console_scripts]\nda = cli:main\ndl = cli:main\n"

    records = []
    with zipfile.ZipFile(wheel_path, "w", zipfile.ZIP_DEFLATED) as whl:
        def add_bytes(arcname: str, data: bytes) -> None:
            whl.writestr(arcname, data)
            records.append(_record_entry(arcname, data))

        def add_file(path: Path, arcname: str) -> None:
            add_bytes(arcname, path.read_bytes())

        add_file(ROOT / "cli.py", "cli.py")
        for pkg in ("core", "drivers"):
            for path in sorted((ROOT / pkg).rglob("*.py")):
                if "__pycache__" not in path.parts:
                    add_file(path, str(path.relative_to(ROOT)).replace("\\", "/"))

        skill_root = ROOT / "skills" / "download-anything"
        for path in sorted(skill_root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and not path.name.startswith("."):
                rel = str(path.relative_to(skill_root)).replace("\\", "/")
                add_file(path, f"share/download-anything/skill/{rel}")

        add_bytes(f"{dist_info}/METADATA", metadata)
        add_bytes(f"{dist_info}/WHEEL", wheel_meta)
        add_bytes(f"{dist_info}/entry_points.txt", entry_points)
        add_bytes(f"{dist_info}/licenses/LICENSE", license_text.encode("utf-8"))
        records.append(f"{dist_info}/RECORD,,")
        whl.writestr(f"{dist_info}/RECORD", ("\n".join(records) + "\n").encode("utf-8"))


def main():
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)[1]
    installer = (ROOT / "skills/download-anything/scripts/install.py").read_text(encoding="utf-8")
    if not re.search(r'^SKILL_VERSION = "' + re.escape(version) + r'"$', installer, re.M):
        raise RuntimeError("Installer SKILL_VERSION must match project version")
    wheel = output / f"download_anything-{version}-py3-none-any.whl"
    uv = shutil.which("uv")
    built_via_tool = False
    if uv:
        try:
            subprocess.run([uv, "build", "--wheel", "--out-dir", str(output)], cwd=ROOT, check=True)
            built_via_tool = True
        except Exception:
            built_via_tool = False
    if not built_via_tool:
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", str(ROOT), "--wheel-dir", str(output)],
                cwd=ROOT,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            built_via_tool = True
        except Exception:
            built_via_tool = False
    if not built_via_tool:
        _build_wheel_stdlib(wheel, version)

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
