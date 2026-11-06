"""Tiny real media fixtures so success tests exercise parseable containers."""
import shutil
import subprocess
import io
import zipfile

import pytest


@pytest.fixture(autouse=True)
def disable_live_baidu_browser(monkeypatch):
    # Browser capture is tested with a fake executable/process, never a live account.
    monkeypatch.setenv("DA_BAIDU_BROWSER", "0")


@pytest.fixture(autouse=True)
def isolate_live_services(monkeypatch, tmp_path):
    """Tests may use loopback servers and explicit mocks, never user accounts."""
    import os
    from urllib.parse import urlsplit
    import requests
    from core.credentials import credentials_manager
    for key in os.environ:
        if key.endswith("_COOKIE"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(credentials_manager, "USER_CRED_DIR", tmp_path / "credentials")
    monkeypatch.setattr(credentials_manager, "config_dir", tmp_path / "config")
    monkeypatch.setattr(credentials_manager, "_cached_yaml", {})
    monkeypatch.setattr(credentials_manager, "_browser_cookie_cache", {})
    for method in ("_harvest_from_browsers", "_harvest_from_desktop_apps", "_query_keychain"):
        monkeypatch.setattr(credentials_manager, method, lambda *a, **kw: None)
    real_request = requests.Session.request

    def offline_request(self, method, url, *args, **kwargs):
        if urlsplit(url).hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise AssertionError("Live HTTP disabled in tests; mock the backend explicitly")
        return real_request(self, method, url, *args, **kwargs)
    monkeypatch.setattr(requests.Session, "request", offline_request)
    real_popen = subprocess.Popen
    class OfflinePopen(real_popen):
        def __init__(self, command, *args, **kwargs):
            if isinstance(command, (list, tuple)) and Path(str(command[0])).name == "curl":
                urls = [arg for arg in command if isinstance(arg, str) and arg.startswith(("http://", "https://"))]
                if any(urlsplit(url).hostname not in {"127.0.0.1", "localhost", "::1"} for url in urls):
                    raise AssertionError("Live curl disabled in tests")
            super().__init__(command, *args, **kwargs)
    from pathlib import Path
    monkeypatch.setattr(subprocess, "Popen", OfflinePopen)


@pytest.fixture
def epub_members():
    return {
        "mimetype": b"application/epub+zip",
        "META-INF/container.xml": b'''<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="OEBPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>''',
        "OEBPS/book.opf": b'''<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Minimal Book</dc:title><dc:creator>Test Author</dc:creator></metadata><manifest><item id="chapter" href="text/chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter"/></spine></package>''',
        "OEBPS/text/chapter.xhtml": b'''<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Chapter</title></head><body><p>Readable chapter text.</p></body></html>''',
    }


@pytest.fixture
def ebook_payload(epub_members):
    def make_payload(format_name):
        if format_name == "pdf":
            from pypdf import PdfWriter
            stream = io.BytesIO()
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            writer.write(stream)
            return stream.getvalue()
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for name, content in epub_members.items():
                archive.writestr(name, content)
        return stream.getvalue()
    return make_payload


@pytest.fixture(scope="session")
def media_samples(tmp_path_factory):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg and ffprobe are required for real-media integration tests")
    root = tmp_path_factory.mktemp("media")
    samples = {}
    for ext, codec in [("m4a", "aac"), ("webm", "libopus"), ("ogg", "libvorbis"),
                       ("flac", "flac"), ("wav", "pcm_s16le"), ("mp3", "libmp3lame")]:
        path = root / f"sample.{ext}"
        subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=0.3", "-c:a", codec, str(path)], check=True)
        samples["." + ext] = path.read_bytes()
    video = root / "sample.mp4"
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i",
                    "color=black:size=32x32:duration=0.3", "-c:v", "mpeg4", str(video)], check=True)
    samples[".mp4"] = video.read_bytes()
    return samples
