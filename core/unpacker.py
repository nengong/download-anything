"""
Safe Archive Extraction Engine with Automatic Password Handling
Supports zip, tar, and transparent failover for encrypted archives.
Defends against zip slip (path traversal) vulnerabilities.
"""
import os
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import Optional, List, Dict, Any

class Unpacker:
    """Safely extracts downloaded archives with optional passwords."""

    SUPPORTED_EXTENSIONS = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".7z", ".rar"}

    @classmethod
    def is_archive(cls, file_path: Path) -> bool:
        """Check if file is an archive based on extension and magic headers."""
        if not file_path.exists() or file_path.is_dir():
            return False
        
        ext = "".join(file_path.suffixes).lower()
        if any(ext.endswith(s) for s in cls.SUPPORTED_EXTENSIONS):
            return True

        # Check magic bytes for ZIP and TAR
        try:
            with open(file_path, "rb") as f:
                head = f.read(8)
                if head.startswith(b"PK\x03\x04") or head.startswith(b"7z\xbc\xaf\x27\x1c") or head.startswith(b"Rar!\x1a\x07"):
                    return True
        except Exception:
            pass

        return False

    @classmethod
    def unpack(
        cls,
        archive_path: Path,
        dest_dir: Optional[Path] = None,
        password: Optional[str] = None,
        remove_archive_after: bool = False
    ) -> List[Path]:
        """
        Extract archive into dest_dir (defaults to a subfolder named after archive stem).
        Returns list of extracted file paths.
        """
        if not archive_path.exists():
            return []

        if dest_dir is None:
            dest_dir = archive_path.parent / f"extracted_{archive_path.stem}"

        dest_dir.mkdir(parents=True, exist_ok=True)
        extracted_files: List[Path] = []

        # 1. Try ZIP
        if zipfile.is_zipfile(archive_path):
            extracted_files = cls._unpack_zip(archive_path, dest_dir, password)

        # 2. Try TAR
        elif tarfile.is_tarfile(archive_path):
            extracted_files = cls._unpack_tar(archive_path, dest_dir)

        # 3. Fallback to system 7z / unar if available
        if not extracted_files:
            extracted_files = cls._unpack_external(archive_path, dest_dir, password)

        if extracted_files and remove_archive_after:
            try:
                archive_path.unlink(missing_ok=True)
            except Exception:
                pass

        return extracted_files

    @classmethod
    def _unpack_zip(cls, archive_path: Path, dest_dir: Path, password: Optional[str]) -> List[Path]:
        files: List[Path] = []
        pw_bytes_candidates = []
        if password:
            pw_bytes_candidates = [
                password.encode("utf-8"),
                password.encode("gbk", errors="ignore"),
                password.encode("cp437", errors="ignore")
            ]
        else:
            pw_bytes_candidates = [None]

        with zipfile.ZipFile(archive_path) as zf:
            success = False
            for pwd in pw_bytes_candidates:
                try:
                    for member in zf.infolist():
                        # Prevent Zip Slip directory traversal vulnerability
                        member_path = Path(member.filename)
                        if member_path.is_absolute() or ".." in member_path.parts:
                            continue
                        
                        target_file = dest_dir / member_path
                        if member.is_dir():
                            target_file.mkdir(parents=True, exist_ok=True)
                        else:
                            target_file.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(member, "r", pwd=pwd) as source, open(target_file, "wb") as target:
                                shutil.copyfileobj(source, target)
                            files.append(target_file)
                    success = True
                    break
                except (RuntimeError, zipfile.BadZipFile):
                    # Password mismatch, try next candidate
                    files.clear()
                    continue

        return files

    @classmethod
    def _unpack_tar(cls, archive_path: Path, dest_dir: Path) -> List[Path]:
        files: List[Path] = []
        with tarfile.open(archive_path) as tf:
            for member in tf.getmembers():
                member_path = Path(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    continue
                target = dest_dir / member_path
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    f = tf.extractfile(member)
                    if f:
                        with open(target, "wb") as out:
                            shutil.copyfileobj(f, out)
                        files.append(target)
        return files

    @classmethod
    def _unpack_external(cls, archive_path: Path, dest_dir: Path, password: Optional[str]) -> List[Path]:
        """External 7z / unar / unzip tool fallback for complex .7z, .rar, or AES-256 archives."""
        seven_zip = shutil.which("7z") or shutil.which("7za")
        if seven_zip:
            cmd = [seven_zip, "x", f"-o{dest_dir}", "-y", str(archive_path)]
            if password:
                cmd.append(f"-p{password}")
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=True)
                return [p for p in dest_dir.rglob("*") if p.is_file()]
            except Exception:
                pass

        unzip_tool = shutil.which("unzip")
        if unzip_tool and zipfile.is_zipfile(archive_path):
            cmd = [unzip_tool, "-o", str(archive_path), "-d", str(dest_dir)]
            if password:
                cmd.insert(1, f"-P{password}")
                cmd.insert(1, "-q")
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=True)
                return [p for p in dest_dir.rglob("*") if p.is_file()]
            except Exception:
                pass

        return []
