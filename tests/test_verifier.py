"""
Unit Tests for Content Integrity Verifier
"""
import io
import zipfile
from pathlib import Path
from PIL import Image
from core.verifier import Verifier

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

def test_verify_zip_and_epub(tmp_path):
    epub_file = tmp_path / "sample.epub"
    with zipfile.ZipFile(epub_file, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", "<container/>")
    res = Verifier.verify(epub_file, expected_ext="epub")
    assert res.valid
    assert res.detected_type == "epub"

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
