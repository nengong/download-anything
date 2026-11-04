"""Bounded ZIP/TAR extraction. Archive links and external unpackers are not used."""
import os
import re
import stat
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Optional, List

from core.exceptions import ExtractionError, FileTooLargeError


class Unpacker:
    SUPPORTED_EXTENSIONS = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".7z", ".rar"}
    MAX_EXTRACTED_BYTES = 500 * 1024 * 1024
    MAX_MEMBERS = 10000

    @classmethod
    def is_archive(cls, file_path: Path) -> bool:
        if not file_path.is_file():
            return False
        if file_path.suffix.lower() in cls.SUPPORTED_EXTENSIONS:
            return True
        with file_path.open("rb") as source:
            return source.read(8).startswith((b"PK\x03\x04", b"7z\xbc\xaf\x27\x1c", b"Rar!\x1a\x07"))

    @staticmethod
    def _target(base: Path, name: str) -> Optional[Path]:
        path = PurePosixPath(name.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", name):
            return None
        target = base.joinpath(*path.parts)
        for candidate in [target, *target.parents]:
            if candidate == base.parent:
                break
            if candidate.is_symlink():
                raise ExtractionError("Archive destination contains a symbolic link")
        try:
            target.resolve().relative_to(base)
        except ValueError:
            raise ExtractionError("Archive entry escapes the extraction directory")
        return target

    @classmethod
    def _write(cls, source, target: Path, budget: list) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
        try:
            with os.fdopen(os.open(target, flags, 0o600), "wb") as output:
                while chunk := source.read(65536):
                    budget[0] += len(chunk)
                    if budget[0] > cls.MAX_EXTRACTED_BYTES:
                        raise FileTooLargeError("Archive exceeds unpacked byte limit")
                    output.write(chunk)
        except BaseException:
            target.unlink(missing_ok=True)
            raise

    @classmethod
    def _check_budget(cls, sizes: list) -> None:
        if len(sizes) > cls.MAX_MEMBERS or sum(sizes) > cls.MAX_EXTRACTED_BYTES:
            raise FileTooLargeError("Archive exceeds unpacked size or member limit")

    @classmethod
    def unpack(cls, archive_path: Path, dest_dir: Optional[Path] = None,
               password: Optional[str] = None, remove_archive_after: bool = False) -> List[Path]:
        if not archive_path.exists():
            return []
        dest_dir = dest_dir or archive_path.parent / f"extracted_{archive_path.stem}"
        if dest_dir.is_symlink():
            raise ExtractionError("Extraction root must not be a symbolic link")
        dest_dir.mkdir(parents=True, exist_ok=True)
        base = dest_dir.resolve()
        files = []
        budget = [0]
        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path) as archive:
                members = archive.infolist()
                cls._check_budget([member.file_size for member in members])
                for member in members:
                    if stat.S_ISLNK(member.external_attr >> 16):
                        raise ExtractionError("Archive symbolic links are not supported")
                    target = cls._target(base, member.filename)
                    if target is None:
                        continue
                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    candidates = [None] if password is None else list(dict.fromkeys(
                        password.encode(encoding, errors="ignore") for encoding in ("utf-8", "gbk", "cp437")))
                    for index, pwd in enumerate(candidates):
                        try:
                            with archive.open(member, pwd=pwd) as source:
                                cls._write(source, target, budget)
                            break
                        except RuntimeError as exc:
                            if index == len(candidates) - 1:
                                raise ExtractionError("ZIP password is missing or incorrect") from exc
                    files.append(target)
        elif tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path) as archive:
                members = []
                for member in archive:
                    members.append(member)
                    if len(members) > cls.MAX_MEMBERS:
                        raise FileTooLargeError("Archive exceeds member limit")
                cls._check_budget([member.size for member in members])
                for member in members:
                    if not (member.isdir() or member.isreg()):
                        raise ExtractionError("TAR links and special files are not supported")
                    target = cls._target(base, member.name)
                    if target is None:
                        continue
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        with archive.extractfile(member) as source:
                            cls._write(source, target, budget)
                        files.append(target)
        else:
            raise ExtractionError("Safe automatic extraction supports ZIP and TAR only; use --no-unzip to keep this archive")
        if files and remove_archive_after:
            archive_path.unlink()
        return files
