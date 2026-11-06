"""
Deep Content Integrity and Magic Byte Verifier
"""
import zipfile
import json
import math
import shutil
import subprocess
import posixpath
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any

from core.exceptions import VerificationError

@dataclass
class VerificationResult:
    valid: bool
    detected_type: str
    size_bytes: int
    error_message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

def detect_audio_container(head: bytes) -> Optional[str]:
    """Return the audio container implied by its header, or None if unknown."""
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "mp3"
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return "m4a"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    if head.startswith(b"OggS"):
        return "ogg"
    if head.startswith(b"fLaC"):
        return "flac"
    if head.startswith(b"RIFF") and b"WAVE" in head[:16]:
        return "wav"
    return None


def detect_ebook_format(path: Path) -> Optional[str]:
    """Inspect ebook signatures without changing the file or trusting its suffix."""
    try:
        with path.open("rb") as source:
            if source.read(5) == b"%PDF-":
                return "pdf"
        with zipfile.ZipFile(path) as archive:
            marker = archive.getinfo("mimetype")
            if marker.file_size == len(b"application/epub+zip") and archive.read(marker) == b"application/epub+zip":
                return "epub"
    except (OSError, KeyError, ValueError, RuntimeError, zipfile.BadZipFile, NotImplementedError):
        pass
    return None


def _epub_member_path(base: str, reference: str) -> str:
    """Resolve an EPUB URL relative to a ZIP member, never outside the archive."""
    url = urlsplit(reference)
    path = unquote(url.path)
    if not path or url.scheme or url.netloc or "\\" in path or "\x00" in path or path.startswith("/"):
        raise ValueError(f"Unsafe EPUB reference: {reference}")
    normalized = posixpath.normpath(posixpath.join(base, path))
    if normalized in (".", "..") or normalized.startswith("../"):
        raise ValueError(f"EPUB reference escapes archive root: {reference}")
    return normalized


class Verifier:
    """Rigorous verification state machine for downloaded micro-assets."""

    HTML_MARKERS = [b"<!DOCTYPE", b"<!doctype", b"<html", b"<HTML"]

    @classmethod
    def verify(
        cls,
        file_path: Path,
        expected_size: Optional[int] = None,
        expected_ext: Optional[str] = None
    ) -> VerificationResult:
        """
        Verify that file on disk is intact, non-empty, matches expected length,
        and conforms to the binary format magic bytes.
        """
        if not file_path.exists():
            return VerificationResult(
                valid=False,
                detected_type="missing",
                size_bytes=0,
                error_message=f"File does not exist: {file_path}"
            )

        actual_size = file_path.stat().st_size
        if actual_size == 0:
            return VerificationResult(
                valid=False,
                detected_type="empty",
                size_bytes=0,
                error_message="File is empty (0 bytes)"
            )

        # 1. Content-Length Match Assertion
        if expected_size is not None and expected_size > 0:
            if actual_size != expected_size:
                return VerificationResult(
                    valid=False,
                    detected_type="size_mismatch",
                    size_bytes=actual_size,
                    error_message=f"Size mismatch: expected {expected_size} bytes, got {actual_size} bytes",
                    details={"expected_size": expected_size, "actual_size": actual_size}
                )

        # Read head & tail chunks for inspection
        with open(file_path, "rb") as f:
            head = f.read(2048)
            f.seek(max(0, actual_size - 2048))
            tail = f.read(2048)

        ext = (expected_ext or file_path.suffix).lower().lstrip(".")

        # 2. HTML Error Trap Detection
        # If the file is not expected to be HTML, but contains HTML markers, it's a 403/captcha/error page.
        if ext not in ("html", "htm"):
            for marker in cls.HTML_MARKERS:
                if marker in head[:256]:
                    return VerificationResult(
                        valid=False,
                        detected_type="html_trap",
                        size_bytes=actual_size,
                        error_message="Server returned an HTML error/captcha page instead of requested binary media."
                    )

        # 3. Format Specific Magic Byte Verifications
        if ext == "pdf":
            return cls._verify_pdf(file_path, head, tail, actual_size)
        elif ext in ("epub", "zip"):
            return cls._verify_zip_container(file_path, actual_size, is_epub=(ext == "epub"))
        elif ext in ("jpg", "jpeg", "png", "webp", "gif"):
            return cls._verify_image(file_path, head, actual_size, ext)
        elif ext in ("mp4", "m4v", "mov", "mkv", "webm", "avi", "flv", "ts"):
            return cls._verify_mp4(file_path, head, actual_size)
        elif ext in ("mp3", "m4a", "aac", "ogg", "opus", "flac", "wav", "audio"):
            return cls._verify_mp3(file_path, head, actual_size)

        # Default generic verification for unknown formats: non-empty, passed size check
        return VerificationResult(
            valid=True,
            detected_type=f"binary/{ext or 'generic'}",
            size_bytes=actual_size,
            details={"level": "basic", "head_sample": head[:16].hex()}
        )

    @classmethod
    def _verify_pdf(cls, path: Path, head: bytes, tail: bytes, size: int) -> VerificationResult:
        if not head.startswith(b"%PDF-"):
            return VerificationResult(
                valid=False,
                detected_type="corrupted_pdf",
                size_bytes=size,
                error_message="Invalid PDF header: does not start with %PDF-"
            )
        if b"%%EOF" not in tail:
            return VerificationResult(
                valid=False,
                detected_type="truncated_pdf",
                size_bytes=size,
                error_message="Truncated PDF: missing %%EOF marker in file tail"
            )

        # Optional deep check with pypdf
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            pages = len(reader.pages)
            if pages == 0:
                return VerificationResult(
                    valid=False,
                    detected_type="empty_pdf",
                    size_bytes=size,
                    error_message="PDF contains 0 pages"
                )
            return VerificationResult(
                valid=True,
                detected_type="pdf",
                size_bytes=size,
                details={"page_count": pages}
            )
        except Exception as e:
            return VerificationResult(
                valid=False,
                detected_type="corrupted_pdf",
                size_bytes=size,
                error_message=f"PDF parsing error: {e}"
            )

    @classmethod
    def _verify_zip_container(cls, path: Path, size: int, is_epub: bool = False) -> VerificationResult:
        if not zipfile.is_zipfile(path):
            return VerificationResult(
                valid=False,
                detected_type="invalid_zip",
                size_bytes=size,
                error_message="Invalid archive: failed zipfile container check"
            )
        try:
            with zipfile.ZipFile(path, "r") as zf:
                members = zf.infolist()
                if len(members) > 10000 or sum(m.file_size for m in members) > 500 * 1024 * 1024:
                    return VerificationResult(False, "archive_limit_exceeded", size,
                                              "Archive exceeds the unpacked size or member limit")
                if any(m.flag_bits & 1 for m in members):
                    if is_epub:
                        return VerificationResult(False, "invalid_epub", size,
                                                  "Encrypted EPUB members cannot be verified")
                    return VerificationResult(True, "zip", size,
                                              details={"level": "encrypted-container", "crc_checked": False})
                bad_file = zf.testzip()
                if bad_file:
                    return VerificationResult(
                        valid=False,
                        detected_type="corrupted_zip",
                        size_bytes=size,
                        error_message=f"CRC error detected in archive member: {bad_file}"
                    )
                names = zf.namelist()
                if is_epub:
                    try:
                        details = cls._verify_epub_contents(zf)
                    except (ValueError, KeyError, ET.ParseError) as exc:
                        return VerificationResult(False, "invalid_epub", size, str(exc))
                    return VerificationResult(True, "epub", size, details=details)
                return VerificationResult(
                    valid=True,
                    detected_type="zip",
                    size_bytes=size,
                    details={"file_count": len(names)}
                )
        except Exception as e:
            return VerificationResult(
                valid=False,
                detected_type="corrupted_zip",
                size_bytes=size,
                error_message=f"ZIP verification failed: {e}"
            )

    @classmethod
    def _verify_epub_contents(cls, archive: zipfile.ZipFile) -> Dict[str, Any]:
        member_names = set(archive.namelist())
        if archive.read("mimetype") != b"application/epub+zip":
            raise ValueError("Invalid EPUB mimetype")
        container_ns = "{urn:oasis:names:tc:opendocument:xmlns:container}"
        opf_ns = "{http://www.idpf.org/2007/opf}"
        dc_ns = "{http://purl.org/dc/elements/1.1/}"
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        if container.tag != f"{container_ns}container":
            raise ValueError("Invalid EPUB container root")
        rootfiles = container.findall(f"{container_ns}rootfiles/{container_ns}rootfile")
        rootfile = next((item for item in rootfiles
                         if item.get("media-type") == "application/oebps-package+xml"), None)
        if rootfile is None:
            raise ValueError("EPUB container has no OPF rootfile")
        opf_path = _epub_member_path("", rootfile.get("full-path", ""))
        opf = ET.fromstring(archive.read(opf_path))
        if opf.tag != f"{opf_ns}package":
            raise ValueError("Invalid EPUB OPF package root")
        manifest = opf.findall(f"{opf_ns}manifest/{opf_ns}item")
        spine = opf.findall(f"{opf_ns}spine/{opf_ns}itemref")
        if not manifest or not spine:
            raise ValueError("EPUB manifest and spine must be non-empty")
        items = {}
        for item in manifest:
            item_id = item.get("id")
            if not item_id or item_id in items:
                raise ValueError("Missing or duplicate EPUB manifest ID")
            member = _epub_member_path(posixpath.dirname(opf_path), item.get("href", ""))
            if member not in member_names:
                raise ValueError(f"Missing EPUB manifest resource: {member}")
            items[item_id] = (member, item.get("media-type"))
        readable = False
        for itemref in spine:
            if itemref.get("idref") not in items:
                raise ValueError("EPUB spine references a missing manifest item")
            member, media_type = items[itemref.get("idref")]
            if media_type == "image/svg+xml":
                svg = ET.fromstring(archive.read(member))
                if svg.tag != "{http://www.w3.org/2000/svg}svg":
                    raise ValueError("Invalid SVG spine document")
                readable = readable or bool(list(svg))
                continue
            if media_type not in ("application/xhtml+xml", "text/html"):
                raise ValueError("EPUB spine item is not a text document")
            content = archive.read(member)
            if media_type == "application/xhtml+xml":
                ET.fromstring(content)
            soup = BeautifulSoup(content, "html.parser")
            body = soup.find("body")
            if body is None:
                raise ValueError(f"EPUB document lacks a body: {member}")
            for hidden in body.find_all(["script", "style"]):
                hidden.decompose()
            readable = readable or any(char.isalnum() for char in body.get_text(" ", strip=True))
            readable = readable or any(
                tag.get("src") or tag.get("data") or (tag.name == "svg" and tag.find())
                for tag in body.find_all(["img", "object", "svg", "video", "audio"])
            )
        if not readable:
            raise ValueError("EPUB spine contains no readable text or visual content")
        metadata = opf.find(f"{opf_ns}metadata")
        def metadata_text(tag):
            if metadata is None:
                return ""
            return "; ".join("".join(node.itertext()).strip()
                             for node in metadata.findall(f"{dc_ns}{tag}"))
        return {"file_count": len(archive.namelist()), "title": metadata_text("title"),
                "author": metadata_text("creator"), "spine_count": len(spine)}

    @classmethod
    def _verify_image(cls, path: Path, head: bytes, size: int, ext: str) -> VerificationResult:
        try:
            from PIL import Image
            with Image.open(path) as img:
                img.verify()
                format_name = img.format
                width, height = img.size
                return VerificationResult(
                    valid=True,
                    detected_type=f"image/{format_name.lower()}",
                    size_bytes=size,
                    details={"format": format_name, "dimensions": f"{width}x{height}"}
                )
        except Exception as e:
            return VerificationResult(
                valid=False,
                detected_type=f"corrupted_image_{ext}",
                size_bytes=size,
                error_message=f"Image decoding failed: {e}"
            )

    @classmethod
    def _verify_mp4(cls, path: Path, head: bytes, size: int) -> VerificationResult:
        return cls._verify_media(path, size, "video")

    @classmethod
    def _verify_mp3(cls, path: Path, head: bytes, size: int) -> VerificationResult:
        return cls._verify_media(path, size, "audio")

    @classmethod
    def _verify_media(cls, path: Path, size: int, media_type: str) -> VerificationResult:
        probe = shutil.which("ffprobe")
        if not probe:
            return VerificationResult(False, "unverified_media", size,
                                      "ffprobe is required to validate audio/video; install FFmpeg")
        try:
            result = subprocess.run(
                [probe, "-v", "error", "-count_packets", "-show_streams", "-show_format",
                 "-of", "json", str(path)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode or result.stderr.strip():
                raise ValueError("ffprobe reported invalid or truncated media")
            info = json.loads(result.stdout)
            if media_type == "video" and path.suffix.lower() in {".webm", ".mkv"} and not any(
                s.get("codec_type") == "video" for s in info.get("streams", [])
            ):
                media_type = "audio"
            media_streams = [
                s for s in info.get("streams", [])
                if s.get("codec_type") in ("video", "audio")
                and not s.get("disposition", {}).get("attached_pic")
            ]
            streams = [s for s in media_streams if s.get("codec_type") == media_type]
            if not streams or not any(int(s.get("nb_read_packets", 0)) > 0 for s in streams):
                raise ValueError(f"No readable {media_type} packets")
            fmt = info.get("format", {})
            duration = float(fmt.get("duration") or streams[0].get("duration") or 0)
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError("Missing or invalid media duration")
            container = fmt.get("format_name", "unknown")
            name = ("m4a" if media_type == "audio" else "mp4") if "mov,mp4" in container else (
                "webm" if "webm" in container else container.split(",")[0])
            return VerificationResult(True, f"{media_type}/{name}", size, details={
                "level": "media-structure", "duration_seconds": duration,
                "container": container, "stream_count": len(media_streams),
                "has_audio": any(s.get("codec_type") == "audio" for s in media_streams),
            })
        except (OSError, subprocess.SubprocessError, ValueError, TypeError) as exc:
            return VerificationResult(False, f"corrupted_{media_type}", size, str(exc))
