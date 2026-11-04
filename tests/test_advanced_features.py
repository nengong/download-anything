"""
Unit Tests for Advanced Capabilities:
- Local Deduplication (AssetIndexDB & dirty share text cache hit)
- Knowledge-Base Sync (VaultSync for Obsidian & Notion with duplicate filtering)
- Cloud Speech-to-Text Transcription Hook (CloudTranscriber)
- Feishu & Notion Public Document Drivers
- Sidecar .lrc lyrics generation, Bilibili .srt subtitle conversion, and Audio stream container verification
"""
import base64
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import yaml

from core.index_db import AssetIndexDB
from core.exceptions import DAError
from core.vault_sync import VaultSync
from core.transcriber import CloudTranscriber
from core.sidecar import SidecarWriter
from core.verifier import Verifier
from drivers.base import AssetPackage, TargetAsset
from drivers.docs.feishu import FeishuDocDriver
from drivers.docs.notion import NotionPublicDriver
from drivers.social.bilibili import BilibiliDriver
from cli import process_download


class _StubDriver:
    name = "stub"
    category = "test"

    def __init__(self, package):
        self.package = package

    def can_handle(self, url):
        return True

    def extract(self, url, **kwargs):
        return self.package

    def cleanup(self, package):
        pass


def _data_package(filename, payload):
    uri = "data:application/octet-stream;base64," + base64.b64encode(payload).decode("ascii")
    return AssetPackage(
        title="Track",
        platform="stub",
        assets=[TargetAsset(
            url=uri,
            filename=filename,
            file_type="primary",
            expected_size=len(payload),
        )],
        metadata={},
    )

def test_asset_index_db_caching_and_dirty_share_hit(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        tpath = Path(td)
        monkeypatch.setattr(AssetIndexDB, "DB_DIR", tpath)
        monkeypatch.setattr(AssetIndexDB, "DB_PATH", tpath / "test_index.db")

        dummy_file = tpath / "test_video.mp4"
        dummy_file.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 4096)

        url = "https://b23.tv/BV1test12345"
        
        # 1. Query before recording -> None
        assert AssetIndexDB.query(url) is None

        # 2. Record successful download with canonical URL
        AssetIndexDB.record(
            url=url,
            platform="bilibili",
            title="Test Video",
            output_dir=tpath,
            primary_file=dummy_file,
            size_bytes=dummy_file.stat().st_size,
            sidecars={"cover": str(tpath / "cover.jpg")}
        )

        # 3. Query with dirty mobile share text in process_download -> Hit cache
        dirty_share = "【B站精选】快来看这个视频 https://b23.tv/BV1test12345 转发收藏！"
        hit = process_download(dirty_share, agent_mode=True)
        assert hit is not None
        assert hit["status"] == "cached"
        assert hit["cached"] is True
        assert hit["title"] == "Test Video"
        assert hit["primary_asset"] == str(dummy_file.resolve())

def test_vault_sync_obsidian_deduplication():
    with tempfile.TemporaryDirectory() as td:
        tpath = Path(td)
        vault_dir = tpath / "MyVault"
        vault_dir.mkdir(parents=True, exist_ok=True)
        (vault_dir / ".obsidian").mkdir()

        asset_dir = tpath / "2026-11-04_AgentArticle"
        asset_dir.mkdir()
        # Simulate both generic content.md and named note
        (asset_dir / "content.md").write_text("# Generic\n\nBody.", encoding="utf-8")
        (asset_dir / "content.info.json").write_text("{}", encoding="utf-8")
        note = asset_dir / "My_Awesome_Article.md"
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
        assert synced_note.name == "My_Awesome_Article.md"
        # Ensure redundant generic content.md was skipped
        assert not (synced_note.parent / "content.md").exists()
        content = synced_note.read_text(encoding="utf-8")
        assert "---" in content
        assert yaml.safe_load(content.split("---", 2)[1])["platform"] == "web_article"

def test_sidecar_lyrics_lrc_generation(tmp_path):
    primary = TargetAsset(url="https://example.com/song.mp3", filename="晴天.mp3", file_type="primary")
    pkg = AssetPackage(
        title="晴天 - 周杰伦",
        platform="music_163",
        assets=[primary],
        metadata={
            "original_url": "https://music.163.com/#/song?id=186016",
            "lyrics": "[00:00.00] 故事的小黄花\n[00:04.50] 从出生那年就飘着"
        }
    )
    sidecars = SidecarWriter.write_sidecars(tmp_path, pkg, primary_filename="晴天.mp3")
    assert "lyrics" in sidecars
    assert sidecars["lyrics"].exists()
    assert sidecars["lyrics"].name == "晴天.lrc"
    assert "故事的小黄花" in sidecars["lyrics"].read_text(encoding="utf-8")

def test_verifier_modern_audio_containers(tmp_path):
    # M4A container saved with .mp3 extension (e.g. from yt-dlp fallback without ffmpeg)
    m4a_as_mp3 = tmp_path / "track.mp3"
    m4a_as_mp3.write_bytes(b"\x00\x00\x00\x20ftypM4A \x00\x00\x02\x00isomiso2")
    res_m4a = Verifier.verify(m4a_as_mp3, expected_ext="mp3")
    assert not res_m4a.valid

    # WebM/Opus container saved with .mp3 extension
    webm_as_mp3 = tmp_path / "track2.mp3"
    webm_as_mp3.write_bytes(b"\x1a\x45\xdf\xa3\x01\x00\x00\x00\x00\x00\x00\x1f")
    res_webm = Verifier.verify(webm_as_mp3, expected_ext="mp3")
    assert not res_webm.valid


def test_process_download_rejects_unsafe_primary_filename(tmp_path):
    package = _data_package("../escaped.txt", b"unsafe")
    driver = _StubDriver(package)
    with patch("cli.get_default_drivers", return_value=[driver]), \
         patch("cli.AssetIndexDB.query", return_value=None), \
         patch("cli.AssetIndexDB.record"):
        with pytest.raises(DAError, match="Unsafe asset filename"):
            process_download(
                "https://example.com/unsafe",
                output_dir=str(tmp_path),
                no_sidecar=True,
                agent_mode=True,
            )
    assert not (tmp_path / "escaped.txt").exists()


@pytest.mark.parametrize(
    "expected_suffix", [".m4a", ".webm", ".ogg", ".flac", ".wav"],
)
def test_failed_mp3_transcode_preserves_real_audio_extension(tmp_path, media_samples, expected_suffix):
    payload = media_samples[expected_suffix]
    package = _data_package("content.mp3", payload)
    driver = _StubDriver(package)
    with patch("cli.get_default_drivers", return_value=[driver]), \
         patch("cli.AssetIndexDB.query", return_value=None), \
         patch("cli.AssetIndexDB.record"), \
         patch("cli.MusicUnlocker.transcode_to_mp3", return_value=False):
        result = process_download(
            "https://example.com/audio",
            output_dir=str(tmp_path),
            no_sidecar=True,
            agent_mode=True,
        )

    primary = Path(result["primary_asset"])
    assert result["status"] == "success"
    assert primary.suffix == expected_suffix
    assert primary.exists()
    assert primary.stat().st_size == len(payload)
    assert not primary.with_suffix(".mp3").exists()
    assert not primary.with_suffix(".raw_audio").exists()


def test_audio_only_cache_variant_is_independent(tmp_path, monkeypatch):
    monkeypatch.setattr(AssetIndexDB, "DB_DIR", tmp_path)
    monkeypatch.setattr(AssetIndexDB, "DB_PATH", tmp_path / "index.db")
    video = tmp_path / "video.mp4"
    audio = tmp_path / "audio.m4a"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    url = "https://example.com/asset"

    AssetIndexDB.record(url, "test", "Default", tmp_path, video, 5)
    AssetIndexDB.record(url, "test", "Audio", tmp_path, audio, 5, variant="audio-only")

    assert AssetIndexDB.query(url)["primary_asset"] == str(video.resolve())
    assert AssetIndexDB.query(url, variant="audio-only")["primary_asset"] == str(audio.resolve())


@pytest.mark.parametrize(
    "options",
    [
        {"transcribe": True},
        {"vault": "/tmp/vault"},
        {"notion": True},
        {"output_dir": "/tmp/new-output"},
    ],
)
def test_cache_hit_does_not_suppress_requested_postprocessing(options):
    cached = {"status": "cached", "cached": True, "primary_asset": "/tmp/original"}
    with patch("cli.AssetIndexDB.query", return_value=cached) as query, \
         patch("cli.Router.find_driver", side_effect=RuntimeError("cache bypassed")):
        with pytest.raises(RuntimeError, match="cache bypassed"):
            process_download("https://example.com/asset", agent_mode=True, **options)
    query.assert_not_called()


def test_audio_only_queries_dedicated_cache_variant():
    with patch("cli.AssetIndexDB.query", return_value=None) as query, \
         patch("cli.Router.find_driver", side_effect=RuntimeError("stop after cache query")):
        with pytest.raises(RuntimeError, match="stop after cache query"):
            process_download("https://example.com/asset", agent_mode=True, audio_only=True)
    assert query.call_args_list
    assert all(
        call.args == ("https://example.com/asset",) and call.kwargs == {"variant": "audio-only"}
        for call in query.call_args_list
    )


def test_audio_only_failure_preserves_video_and_reports_error(tmp_path):
    package = _data_package("content.mp4", b"\x00" * 2000)
    driver = _StubDriver(package)
    with patch("cli.get_default_drivers", return_value=[driver]), \
         patch("cli.AssetIndexDB.query", return_value=None), \
         patch("cli.AssetIndexDB.record"), \
         patch("cli._extract_audio_from_video", return_value=None):
        with pytest.raises(DAError, match="Audio extraction failed"):
            process_download(
                "https://example.com/video",
                output_dir=str(tmp_path),
                audio_only=True,
                no_sidecar=True,
                agent_mode=True,
            )

    videos = list(tmp_path.rglob("Track.mp4"))
    assert len(videos) == 1
    assert videos[0].stat().st_size == 2000


def test_bilibili_subtitle_srt_conversion(monkeypatch):
    driver = BilibiliDriver()
    assert driver._format_srt_time(65.432) == "00:01:05,432"

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "player/v2" in url:
            resp.json.return_value = {
                "code": 0,
                "data": {"subtitle": {"subtitles": [{"subtitle_url": "//i0.hdslb.com/bfs/subtitle/test.json"}]}}
            }
        else:
            resp.json.return_value = {
                "body": [
                    {"from": 0.5, "to": 2.8, "content": "第一句字幕"},
                    {"from": 3.0, "to": 5.2, "content": "第二句字幕"}
                ]
            }
        return resp

    session = MagicMock()
    session.get.side_effect = mock_get
    sub_asset = driver._fetch_subtitles("BV1xx411c7mD", 12345, session)
    assert sub_asset is not None
    assert sub_asset.filename == "subtitle.srt"
    assert sub_asset.url.startswith("data:text/plain;charset=utf-8;base64,")
    decoded = base64.b64decode(sub_asset.url.split(",", 1)[1]).decode("utf-8")
    assert "00:00:00,500 --> 00:00:02,800" in decoded
    assert "第一句字幕" in decoded

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
