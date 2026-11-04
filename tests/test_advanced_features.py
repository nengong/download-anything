"""
Unit Tests for Advanced Capabilities:
- Local Deduplication (AssetIndexDB)
- Knowledge-Base Sync (VaultSync for Obsidian & Notion)
- Cloud Speech-to-Text Transcription Hook (CloudTranscriber)
- Feishu & Notion Public Document Drivers
"""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from core.index_db import AssetIndexDB
from core.vault_sync import VaultSync
from core.transcriber import CloudTranscriber
from drivers.docs.feishu import FeishuDocDriver
from drivers.docs.notion import NotionPublicDriver

def test_asset_index_db_caching(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        tpath = Path(td)
        # Point DB path to temporary dir
        monkeypatch.setattr(AssetIndexDB, "DB_DIR", tpath)
        monkeypatch.setattr(AssetIndexDB, "DB_PATH", tpath / "test_index.db")

        # Create dummy downloaded file
        dummy_file = tpath / "test_video.mp4"
        dummy_file.write_bytes(b"\x00" * 4096)

        url = "https://b23.tv/BV1test12345"
        
        # 1. Query before recording -> None
        assert AssetIndexDB.query(url) is None

        # 2. Record successful download
        AssetIndexDB.record(
            url=url,
            platform="bilibili",
            title="Test Video",
            output_dir=tpath,
            primary_file=dummy_file,
            size_bytes=4096,
            sidecars={"cover": str(tpath / "cover.jpg")}
        )

        # 3. Query after recording -> Hit cache
        hit = AssetIndexDB.query(url)
        assert hit is not None
        assert hit["status"] == "cached"
        assert hit["cached"] is True
        assert hit["title"] == "Test Video"
        assert hit["primary_asset"] == str(dummy_file.resolve())
        assert hit["size_bytes"] == 4096

def test_vault_sync_obsidian():
    with tempfile.TemporaryDirectory() as td:
        tpath = Path(td)
        # Create mock Obsidian vault
        vault_dir = tpath / "MyVault"
        vault_dir.mkdir(parents=True, exist_ok=True)
        (vault_dir / ".obsidian").mkdir()

        # Create mock asset folder
        asset_dir = tpath / "2026-11-04_AgentArticle"
        asset_dir.mkdir()
        note = asset_dir / "article.md"
        note.write_text("# My Awesome Article\n\nSome body text.", encoding="utf-8")
        cover = asset_dir / "cover.jpg"
        cover.write_bytes(b"\xff\xd8\xff")

        synced_note = VaultSync.sync_to_obsidian(
            asset_dir=asset_dir,
            vault_path=str(vault_dir),
            title="My Awesome Article",
            platform="web_article",
            original_url="https://example.com/article"
        )

        assert synced_note is not None
        assert synced_note.exists()
        # Verify YAML frontmatter injection
        content = synced_note.read_text(encoding="utf-8")
        assert "---" in content
        assert "platform: \"web_article\"" in content
        assert "tags:" in content
        assert "download-anything" in content

def test_cloud_transcriber_groq_mock(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        tpath = Path(td)
        audio = tpath / "speech.mp3"
        audio.write_bytes(b"\x00" * 5000)

        monkeypatch.setenv("GROQ_API_KEY", "gsk_test123456789")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "text": "Hello world this is an AI podcast",
            "segments": [
                {"start": 0.0, "end": 2.5, "text": "Hello world"},
                {"start": 2.5, "end": 5.0, "text": "this is an AI podcast"}
            ]
        }
        monkeypatch.setattr("requests.post", lambda *args, **kwargs: mock_resp)

        transcript_file = CloudTranscriber.transcribe(audio, tpath, "Test_Speech")
        assert transcript_file is not None
        assert transcript_file.exists()
        content = transcript_file.read_text(encoding="utf-8")
        assert "语音文字稿" in content
        assert "[00:00]" in content
        assert "Hello world" in content

def test_feishu_driver_can_handle():
    driver = FeishuDocDriver()
    assert driver.can_handle("https://bytedance.feishu.cn/docx/doxcn12345678")
    assert driver.can_handle("https://company.feishu.cn/wiki/wikcn87654321")
    assert driver.can_handle("https://app.larksuite.com/docx/doxus99999")
    assert not driver.can_handle("https://music.163.com")

def test_notion_driver_can_handle():
    driver = NotionPublicDriver()
    assert driver.can_handle("https://antigravity.notion.site/Guide-1234567890abcdef")
    assert driver.can_handle("https://www.notion.so/My-Project-Plan-067dd719a912471ea9a3ac2f029e4720")
    assert not driver.can_handle("https://bilibili.com")
