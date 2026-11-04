"""
Deep Content Integrity and Magic Byte Verifier
"""
import zipfile
import json
import math
import shutil
import subprocess
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
                    if "META-INF/container.xml" not in names and "mimetype" not in names:
                        return VerificationResult(
                            valid=False,
                            detected_type="invalid_epub",
                            size_bytes=size,
                            error_message="Archive is valid ZIP but lacks EPUB container markers"
                        )
                    return VerificationResult(
                        valid=True,
                        detected_type="epub",
                        size_bytes=size,
                        details={"file_count": len(names)}
                    )
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
            streams = [s for s in info.get("streams", []) if s.get("codec_type") == media_type
                       and not s.get("disposition", {}).get("attached_pic")]
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
                "container": container, "stream_count": len(streams),
            })
        except (OSError, subprocess.SubprocessError, ValueError, TypeError) as exc:
            return VerificationResult(False, f"corrupted_{media_type}", size, str(exc))
