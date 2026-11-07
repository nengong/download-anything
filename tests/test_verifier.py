"""
Unit Tests for Content Integrity Verifier
"""
import io
import zipfile
from pathlib import Path
from PIL import Image
import pytest
from core.verifier import Verifier, detect_ebook_format

def test_verify_html_trap_detection(tmp_path):
    fake_file = tmp_path / "book.pdf"
    fake_file.write_bytes(b"<!DOCTYPE html><html><body>403 Forbidden Captcha</body></html>")
    res = Verifier.verify(fake_file, expected_ext="pdf")
    assert not res.valid
    assert res.detected_type == "html_trap"

def test_verify_pdf_valid(tmp_path):
    pdf_file = tmp_path / "valid.pdf"
    # Basic minimal valid PDF
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF"
    )
    pdf_file.write_bytes(pdf_content)
    res = Verifier.verify(pdf_file, expected_ext="pdf")
    assert res.valid
    assert res.detected_type == "pdf"

def test_verify_pdf_truncated(tmp_path):
    truncated = tmp_path / "truncated.pdf"
    truncated.write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\nsome incomplete stream data without eof")
    res = Verifier.verify(truncated, expected_ext="pdf")
    assert not res.valid
    assert res.detected_type == "truncated_pdf"

def test_verify_zip_and_epub(tmp_path, ebook_payload):
    epub_file = tmp_path / "sample.epub"
    epub_file.write_bytes(ebook_payload("epub"))
    res = Verifier.verify(epub_file, expected_ext="epub")
    assert res.valid
    assert res.detected_type == "epub"
    assert res.details == {"file_count": 4, "title": "Minimal Book",
                           "author": "Test Author", "spine_count": 1}


@pytest.mark.parametrize("actual,declared", [("epub", "pdf"), ("pdf", "epub"), ("pdf", "pdf")])
def test_detect_ebook_format_ignores_suffix(tmp_path, ebook_payload, actual, declared):
    path = tmp_path / f"book.{declared}"
    payload = ebook_payload(actual)
    path.write_bytes(payload)
    assert detect_ebook_format(path) == actual
    assert path.read_bytes() == payload
    assert Verifier.verify(path, expected_ext=actual).valid


@pytest.mark.parametrize("marker", [None, b"application/zip", b"application/epub+zip\n"])
def test_detect_ebook_format_rejects_ordinary_zip(tmp_path, marker):
    path = tmp_path / "ordinary.epub"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("hello.txt", "Not an ebook")
        if marker is not None:
            archive.writestr("mimetype", marker)
    assert detect_ebook_format(path) is None
    assert not Verifier.verify(path).valid
    assert Verifier.verify(path, expected_ext="zip").valid


@pytest.mark.parametrize("missing", ["mimetype", "META-INF/container.xml", "OEBPS/book.opf",
                                    "OEBPS/text/chapter.xhtml"])
def test_epub_rejects_missing_required_members(tmp_path, epub_members, missing):
    del epub_members[missing]
    path = tmp_path / "missing.epub"
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in epub_members.items():
            archive.writestr(name, content)
    assert not Verifier.verify(path).valid


@pytest.mark.parametrize("member,old,new", [
    ("mimetype", b"application/epub+zip", b"application/zip"),
    ("META-INF/container.xml", b"application/oebps-package+xml", b"text/plain"),
    ("META-INF/container.xml", b"OEBPS/book.opf", b"../book.opf"),
    ("META-INF/container.xml", b"</container>", b""),
    ("OEBPS/book.opf", b'idref="chapter"', b'idref="missing"'),
    ("OEBPS/book.opf", b'<itemref idref="chapter"/>', b""),
    ("OEBPS/book.opf", b'<item id="chapter" href="text/chapter.xhtml" media-type="application/xhtml+xml"/>', b""),
    ("OEBPS/book.opf", b"text/chapter.xhtml", b"../../chapter.xhtml"),
    ("OEBPS/book.opf", b"text/chapter.xhtml", b"%2e%2e/%2e%2e/chapter.xhtml"),
    ("OEBPS/book.opf", b"text/chapter.xhtml", b"/chapter.xhtml"),
    ("OEBPS/book.opf", b"</package>", b""),
    ("OEBPS/text/chapter.xhtml", b"Readable chapter text.", b""),
    ("OEBPS/text/chapter.xhtml", b"</html>", b""),
])
def test_epub_rejects_invalid_structure(tmp_path, epub_members, member, old, new):
    epub_members[member] = epub_members[member].replace(old, new)
    path = tmp_path / "invalid.epub"
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in epub_members.items():
            archive.writestr(name, content)
    result = Verifier.verify(path)
    assert not result.valid
    assert result.detected_type == "invalid_epub"


def test_epub_normalizes_relative_member_paths(tmp_path, epub_members):
    epub_members["OEBPS/book.opf"] = epub_members["OEBPS/book.opf"].replace(
        b"text/chapter.xhtml", b"text/../text/chapter.xhtml")
    path = tmp_path / "normalized.epub"
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in epub_members.items():
            archive.writestr(name, content)
    assert Verifier.verify(path).valid

def test_verify_image(tmp_path):
    img_file = tmp_path / "cover.png"
    img = Image.new("RGB", (100, 100), color="blue")
    img.save(img_file, format="PNG")

    res = Verifier.verify(img_file, expected_ext="png")
    assert res.valid
    assert "png" in res.detected_type

def test_verify_size_mismatch(tmp_path):
    file_path = tmp_path / "data.bin"
    file_path.write_bytes(b"12345")
    res = Verifier.verify(file_path, expected_size=100)
    assert not res.valid
    assert res.detected_type == "size_mismatch"


def test_verify_font_magic_bytes_and_jsdelivr_limit_trap(tmp_path):
    ttf_file = tmp_path / "LXGWWenKai-Regular.ttf"
    ttf_file.write_bytes(b"\x00\x01\x00\x00\x00\x10\x01\x00\x00\x04\x00\x00GPOS")
    res_ttf = Verifier.verify(ttf_file)
    assert res_ttf.valid
    assert res_ttf.detected_type == "font/ttf"

    otf_file = tmp_path / "NotoSansCJKsc-Regular.otf"
    otf_file.write_bytes(b"OTTO\x00\x12\x01\x00\x00\x04\x00\x20CFF ")
    res_otf = Verifier.verify(otf_file)
    assert res_otf.valid
    assert res_otf.detected_type == "font/otf"

    woff2_file = tmp_path / "Inter.woff2"
    woff2_file.write_bytes(b"wOF2\x00\x01\x00\x00\x00\x00\x12\x34")
    res_woff2 = Verifier.verify(woff2_file)
    assert res_woff2.valid
    assert res_woff2.detected_type == "font/woff2"

    trap_file = tmp_path / "TooLarge.ttf"
    trap_file.write_bytes(b"File size exceeded the configured limit of 20 MB.")
    res_trap = Verifier.verify(trap_file)
    assert not res_trap.valid
    assert "corrupted_font" in res_trap.detected_type

