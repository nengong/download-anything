"""
Unit Tests for Phase 5 Features:
- Safe Unpacker (encrypted ZIP, TAR, Zip Slip defense)
- WebArticleDriver (anti-copy stripping, image localization, Markdown export)
- AndroidAPKDriver (F-Droid, Aptoide, Google Play package routing)
- CLI Batch and Audio processing
"""
import io
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from core.unpacker import Unpacker
from drivers.docs.web_article import WebArticleDriver
from drivers.software.apk import AndroidAPKDriver
from cli import _extract_audio_from_video, process_download

def test_unpacker_is_archive():
    with tempfile.TemporaryDirectory() as td:
        tpath = Path(td)
        plain_file = tpath / "note.txt"
        plain_file.write_text("hello")
        assert not Unpacker.is_archive(plain_file)

        zip_f = tpath / "test.zip"
        with zipfile.ZipFile(zip_f, "w") as zf:
            zf.writestr("test.txt", "content")
        assert Unpacker.is_archive(zip_f)

def test_unpacker_standard_zip():
    with tempfile.TemporaryDirectory() as td:
        tpath = Path(td)
        zip_f = tpath / "bundle.zip"
        with zipfile.ZipFile(zip_f, "w") as zf:
            zf.writestr("file1.txt", "first file content")
            zf.writestr("sub/file2.txt", "second file content")

        dest = tpath / "out"
        extracted = Unpacker.unpack(zip_f, dest_dir=dest)
        assert len(extracted) == 2
        assert (dest / "file1.txt").read_text() == "first file content"
        assert (dest / "sub" / "file2.txt").read_text() == "second file content"

def test_unpacker_zip_slip_defense():
    """Verify that entries trying to escape the destination directory are safely dropped."""
    with tempfile.TemporaryDirectory() as td:
        tpath = Path(td)
        zip_f = tpath / "evil.zip"
        with zipfile.ZipFile(zip_f, "w") as zf:
            zf.writestr("../../evil.txt", "malicious payload")
            zf.writestr("legit.txt", "harmless")

        dest = tpath / "sandbox"
        extracted = Unpacker.unpack(zip_f, dest_dir=dest)
        assert len(extracted) == 1
        assert not (tpath / "evil.txt").exists()
        assert (dest / "legit.txt").exists()

def test_unpacker_password_protected_zip():
    with tempfile.TemporaryDirectory() as td:
        tpath = Path(td)
        f = tpath / "payload.txt"
        f.write_text("secret agent data")
        zip_f = tpath / "locked.zip"
        
        # Use macOS/Linux built-in zip to create password protected archive
        cmd = ["zip", "-e", "-P", "Pass9988", str(zip_f), "payload.txt"]
        res = subprocess.run(cmd, cwd=str(tpath), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode == 0:
            dest = tpath / "decrypted"
            extracted = Unpacker.unpack(zip_f, dest_dir=dest, password="Pass9988")
            assert len(extracted) == 1
            assert (dest / "payload.txt").read_text().strip() == "secret agent data"

def test_web_article_driver_can_handle():
    driver = WebArticleDriver()
    assert driver.can_handle("https://zhuanlan.zhihu.com/p/654321")
    assert driver.can_handle("https://blog.csdn.net/test/article/details/999")
    assert driver.can_handle("https://medium.com/@dev/ai-coding-guide")
    assert not driver.can_handle("https://pan.quark.cn/s/12345")
    assert not driver.can_handle("https://www.youtube.com/watch?v=123")

def test_web_article_driver_extract(monkeypatch):
    driver = WebArticleDriver()
    sample_html = """
    <html>
        <head><title>Modern AI Coding - Zhihu</title></head>
        <body>
            <script>var bad = 'strip me';</script>
            <article class="article-content">
                <h1>Understanding Agentic AI Workflows</h1>
                <p>Agents require clean structured representations.</p>
                <img src="https://pic4.zhimg.com/v2-abc12345.jpg" alt="Architecture diagram">
                <pre>def solve():\n    return 42</pre>
            </article>
        </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.text = sample_html
    mock_resp.apparent_encoding = "utf-8"
    mock_resp.headers = {"Date": "Wed, 04 Nov 2026 00:00:00 GMT"}
    monkeypatch.setattr("requests.Session.get", lambda *args, **kwargs: mock_resp)

    pkg = driver.extract("https://zhuanlan.zhihu.com/p/654321")
    assert pkg.platform == "web_article"
    assert "Understanding Agentic AI Workflows" in pkg.title
    assert len(pkg.assets) == 2  # 1 markdown article + 1 localized image
    assert pkg.primary_asset.filename == "article.md"
    assert pkg.assets[1].filename.startswith("img_01")
    assert "Architecture diagram" in pkg.metadata["sidecar_text"]

def test_android_apk_driver_can_handle():
    driver = AndroidAPKDriver()
    assert driver.can_handle("https://play.google.com/store/apps/details?id=com.termux")
    assert driver.can_handle("org.videolan.vlc")
    assert driver.can_handle("apk:com.openai.chatgpt")
    assert not driver.can_handle("script.py")
    assert not driver.can_handle("https://example.com/index.html")

def test_android_apk_driver_fdroid_extract(monkeypatch):
    driver = AndroidAPKDriver()
    fdroid_data = {
        "packageName": "com.termux",
        "name": "Termux",
        "suggestedVersionCode": 1002,
        "packages": [{"versionCode": 1002, "versionName": "0.118.0"}],
        "icon": "icon.png"
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fdroid_data
    monkeypatch.setattr("requests.Session.get", lambda *args, **kwargs: mock_resp)

    pkg = driver.extract("com.termux")
    assert pkg.platform == "android_apk"
    assert "Termux" in pkg.title
    assert pkg.primary_asset.filename == "com.termux_0.118.0.apk"
    assert "https://f-droid.org/repo/com.termux_1002.apk" in pkg.primary_asset.url
    assert "adb install -r" in pkg.metadata["sidecar_text"]

def test_audio_extraction_from_video():
    with tempfile.TemporaryDirectory() as td:
        tpath = Path(td)
        # Create dummy mp4 file
        dummy_mp4 = tpath / "sample.mp4"
        dummy_mp4.write_bytes(b"\x00" * 2000)

        # Mock ffmpeg success
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            target_m4a = tpath / "sample.m4a"
            target_m4a.write_bytes(b"\x00" * 3000)
            res = _extract_audio_from_video(dummy_mp4)
            assert res is not None
            assert res.name == "sample.m4a"
