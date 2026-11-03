"""
Deep Content Integrity and Magic Byte Verifier
"""
import zipfile
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
        elif ext in ("mp4", "m4v", "mov"):
            return cls._verify_mp4(file_path, head, actual_size)
        elif ext in ("mp3", "audio"):
            return cls._verify_mp3(file_path, head, actual_size)

        # Default generic verification for unknown formats: non-empty, passed size check
        return VerificationResult(
            valid=True,
            detected_type=f"binary/{ext or 'generic'}",
            size_bytes=actual_size,
            details={"head_sample": head[:16].hex()}
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
        # ISO Base Media File Format: starts with [4 bytes length] 'ftyp'
        if len(head) >= 8 and head[4:8] == b"ftyp":
            brand = head[8:12].decode("latin-1", errors="ignore")
            return VerificationResult(
                valid=True,
                detected_type="video/mp4",
                size_bytes=size,
                details={"brand": brand}
            )
        return VerificationResult(
            valid=False,
            detected_type="corrupted_mp4",
            size_bytes=size,
            error_message="Missing MP4 ftyp atom in file header"
        )

    @classmethod
    def _verify_mp3(cls, path: Path, head: bytes, size: int) -> VerificationResult:
        if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
            return VerificationResult(
                valid=True,
                detected_type="audio/mp3",
                size_bytes=size,
                details={"has_id3": head.startswith(b"ID3")}
            )
        return VerificationResult(
            valid=False,
            detected_type="corrupted_mp3",
            size_bytes=size,
            error_message="Missing MP3 ID3 header or sync word"
        )
