"""Regressions for the independent release audit; no live accounts are used."""
import base64
import hashlib
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import stat
import tarfile
import threading
from unittest.mock import MagicMock, patch
import zipfile

from click.testing import CliRunner
import pytest
import yaml

from cli import main, process_download
from core.exceptions import DAError, CloudDriveError, DownloadError, ExtractionError, FileTooLargeError, VerificationError
from core.fetcher import Fetcher, FetcherOptions
from core.index_db import AssetIndexDB
from core.unpacker import Unpacker
from core.vault_sync import VaultSync
from core.verifier import Verifier
from drivers.base import BaseDriver, AssetPackage, TargetAsset
from drivers.docs.feishu import FeishuDocDriver
from drivers.pan.baidu import BaiduDriver
from drivers.pan.quark import QuarkDriver


def asset(filename, content, kind="primary"):
    return TargetAsset("data:application/octet-stream;base64," + base64.b64encode(content).decode(),
                       filename, kind, expected_size=len(content))


class StubDriver(BaseDriver):
    name = "audit"
    category = "test"

    def __init__(self, assets):
        self.package = AssetPackage(title="Audit", platform=self.name, assets=assets)
        self.cleaned = False

    def can_handle(self, url):
        return True

    def extract(self, url, **kwargs):
        return self.package

    def cleanup(self, package):
        self.cleaned = True


@pytest.fixture(autouse=True)
def isolate_user_state(monkeypatch, tmp_path):
    monkeypatch.setattr(AssetIndexDB, "DB_DIR", tmp_path / "index")
    monkeypatch.setattr(AssetIndexDB, "DB_PATH", tmp_path / "index/index.db")
    for name in ("OBSIDIAN_VAULT_PATH", "DA_VAULT_PATH", "NOTION_API_KEY", "NOTION_TOKEN", "NOTION_DATABASE_ID"):
        monkeypatch.delenv(name, raising=False)


def run(driver, tmp_path, target="https://example.invalid/audit", **options):
    with patch("cli.get_default_drivers", return_value=[driver]):
        return process_download(target, output_dir=str(tmp_path),
                                agent_mode=True, **options)


@pytest.mark.parametrize("filename", ["README.md", "content.md", "content.info.json"])
def test_sidecars_preserve_primary_bytes_and_reported_size(tmp_path, filename):
    original = b"UNIQUE_BODY_SENTINEL"
    result = run(StubDriver([asset(filename, original)]), tmp_path)
    primary = Path(result["primary_asset"])
    assert primary.read_bytes() == original
    assert primary.stat().st_size == result["size_bytes"] == len(original)
    assert str(primary) not in result["sidecars"].values()


def test_feishu_body_survives_pipeline(tmp_path):
    response = MagicMock(status_code=200, url="https://demo.feishu.cn/docx/demo", headers={},
                         text="<html><title>Doc</title><main><p>UNIQUE_BODY_SENTINEL</p></main></html>")
    with patch("drivers.docs.feishu.requests.Session.get", return_value=response):
        result = run(FeishuDocDriver(), tmp_path, target="https://demo.feishu.cn/docx/demo")
    assert "UNIQUE_BODY_SENTINEL" in Path(result["primary_asset"]).read_text(encoding="utf-8")
    assert "UNIQUE_BODY_SENTINEL" in Path(result["sidecars"]["markdown"]).read_text(encoding="utf-8")


def test_quark_preflight_never_transfers_or_creates_folders(tmp_path):
    response = MagicMock()
    response.json.return_value = {"status": 200, "data": {"list": [
        {"fid": "shared", "file_name": "demo.txt", "size": 4}]}}
    driver = QuarkDriver()
    with patch.object(driver, "_get_cookie", return_value="DUMMY"), \
         patch("drivers.pan.quark.requests.get", return_value=response), \
         patch("drivers.pan.quark.requests.post") as post, \
         patch("cli.get_default_drivers", return_value=[driver]):
        result = process_download("https://pan.quark.cn/s/demo", check=True, agent_mode=True)
    post.assert_not_called()
    assert result["status"] == "dry_run"
    assert result["metadata"]["requires_transfer"] is True
    assert result["primary_asset"]["url"] == ""


def baidu_listing():
    response = MagicMock()
    response.json.return_value = {"errno": 0, "data": {"list": [
        {"fs_id": 1, "server_filename": "existing.txt", "size": 5}], "uk": 2, "shareid": 3}}
    return response


def test_baidu_preflight_never_transfers():
    with patch("drivers.pan.baidu.requests.Session.get", return_value=baidu_listing()), \
         patch("drivers.pan.baidu.requests.Session.post") as post, \
         patch.object(BaiduDriver, "_get_cookie") as cookie:
        package = BaiduDriver().extract("https://pan.baidu.com/s/1demo", inspect_only=True)
    post.assert_not_called()
    cookie.assert_not_called()
    assert package.metadata["requires_transfer"]


def test_baidu_existing_content_is_never_deleted():
    transfer = MagicMock()
    transfer.json.return_value = {"errno": -8, "errmsg": "exists"}
    driver = BaiduDriver()
    with patch.object(driver, "_get_cookie", return_value="DUMMY"), \
         patch.object(driver, "_create_temp_folder"), \
         patch("drivers.pan.baidu.requests.Session.get", return_value=baidu_listing()), \
         patch("drivers.pan.baidu.requests.Session.post", return_value=transfer), \
         patch("drivers.pan.baidu.requests.post") as delete:
        with pytest.raises(CloudDriveError):
            driver.extract("https://pan.baidu.com/s/1demo")
    delete.assert_not_called()


def test_quark_creation_failure_does_not_fall_back_to_root():
    response = MagicMock()
    response.json.return_value = {"status": 500}
    with patch("drivers.pan.quark.requests.post", return_value=response):
        with pytest.raises(CloudDriveError):
            QuarkDriver()._get_or_create_temp_folder({})


def test_quark_extract_failure_cleans_owned_folder():
    detail = MagicMock()
    detail.json.return_value = {"status": 200, "data": {"list": [
        {"fid": "shared", "file_name": "demo.txt", "size": 4}]}}
    failure = MagicMock()
    failure.json.return_value = {"status": 500}
    driver = QuarkDriver()
    with patch.object(driver, "_get_cookie", return_value="DUMMY"), \
         patch.object(driver, "_get_or_create_temp_folder", return_value="owned"), \
         patch("drivers.pan.quark.requests.get", return_value=detail), \
         patch("drivers.pan.quark.requests.post", return_value=failure), \
         patch.object(driver, "cleanup") as cleanup:
        with pytest.raises(CloudDriveError):
            driver.extract("https://pan.quark.cn/s/demo")
    assert cleanup.call_args.args[0].context["owned_temp_dir"] == "owned"


def test_cleanup_runs_after_verification_failure(tmp_path):
    driver = StubDriver([asset("bad.mp4", b"not a video")])
    with pytest.raises(VerificationError):
        run(driver, tmp_path)
    assert driver.cleaned


def test_cleanup_failure_is_partial_and_is_not_cached(tmp_path):
    driver = StubDriver([asset("good.txt", b"good")])
    with patch.object(driver, "cleanup", side_effect=CloudDriveError("delete not confirmed")), \
         patch("cli.AssetIndexDB.record") as record:
        result = run(driver, tmp_path)
    assert result["status"] == "partial"
    assert result["operations"]["cleanup"]["status"] == "error"
    record.assert_not_called()


@pytest.mark.parametrize("name,content", [("bad.mp4", b"\0\0\0\x0cftypisom"), ("bad.mp3", b"ID3")])
def test_fake_media_is_rejected(tmp_path, name, content):
    path = tmp_path / name
    path.write_bytes(content)
    assert not Verifier.verify(path).valid


@pytest.mark.parametrize("ext", [".mp4", ".mp3", ".m4a", ".webm", ".ogg", ".flac", ".wav"])
def test_real_media_is_accepted(tmp_path, media_samples, ext):
    path = tmp_path / ("media" + ext)
    path.write_bytes(media_samples[ext])
    result = Verifier.verify(path)
    assert result.valid, result.error_message
    assert result.details["level"] == "media-structure"


def test_media_without_ffprobe_is_not_reported_verified(tmp_path):
    path = tmp_path / "audio.mp3"
    path.write_bytes(b"ID3")
    with patch("core.verifier.shutil.which", return_value=None):
        result = Verifier.verify(path)
    assert not result.valid
    assert result.detected_type == "unverified_media"


@pytest.fixture
def http_server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            body = b"x" * 65536
            self.send_response(403 if self.path == "/error" else 200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


def test_curl_rejects_http_403(http_server, tmp_path):
    fetcher = Fetcher(FetcherOptions(max_retries=0))
    with pytest.raises(DownloadError):
        fetcher.download(http_server + "/error", tmp_path / "bad.bin")
    assert not (tmp_path / "bad.bin").exists()


def test_curl_rejects_oversize_download(http_server, tmp_path):
    fetcher = Fetcher(FetcherOptions(max_retries=0, max_bytes=32))
    with pytest.raises(FileTooLargeError):
        fetcher.download(http_server + "/big", tmp_path / "bad.bin")
    assert not (tmp_path / "bad.bin").exists()


def test_curl_final_size_guard_runs_even_if_process_already_exited(tmp_path):
    part, final = tmp_path / "a.part", tmp_path / "a.bin"
    part.write_bytes(b"x" * 64)
    process = MagicMock(returncode=0)
    process.poll.return_value = 0
    with patch("core.fetcher.subprocess.Popen", return_value=process):
        with pytest.raises(FileTooLargeError):
            Fetcher(FetcherOptions(max_bytes=32))._download_via_curl("https://example.invalid", part, final, {})
    assert not final.exists()


def test_zip_cannot_follow_existing_destination_symlink(tmp_path):
    outside, dest = tmp_path / "outside", tmp_path / "out"
    outside.mkdir()
    dest.mkdir()
    (dest / "link").symlink_to(outside, target_is_directory=True)
    archive = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("link/escaped.txt", b"bad")
    with pytest.raises(ExtractionError):
        Unpacker.unpack(archive, dest)
    assert not (outside / "escaped.txt").exists()


def test_tar_links_are_rejected(tmp_path):
    archive = tmp_path / "archive.tar"
    with tarfile.open(archive, "w") as tar:
        entry = tarfile.TarInfo("link")
        entry.type = tarfile.SYMTYPE
        entry.linkname = "../outside"
        tar.addfile(entry)
    with pytest.raises(ExtractionError):
        Unpacker.unpack(archive, tmp_path / "out")


def test_zip_unpacked_size_limit(tmp_path, monkeypatch):
    archive = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("large.txt", b"x" * 100)
    monkeypatch.setattr(Unpacker, "MAX_EXTRACTED_BYTES", 32)
    with pytest.raises(FileTooLargeError):
        Unpacker.unpack(archive, tmp_path / "out")


def test_cache_preserves_case_sensitive_paths(tmp_path):
    path = tmp_path / "asset.txt"
    path.write_bytes(b"A")
    AssetIndexDB.record("https://example.invalid/AssetA", "audit", "A", tmp_path, path, 1)
    assert AssetIndexDB.query("https://EXAMPLE.invalid/AssetA") is not None
    assert AssetIndexDB.query("https://example.invalid/asseta") is None


def test_cache_does_not_reuse_legacy_lowercase_collision(tmp_path):
    path = tmp_path / "asset.txt"
    path.write_bytes(b"A")
    url = "https://example.invalid/AssetA"
    old_key = hashlib.sha256(url.lower().encode()).hexdigest()
    with patch.object(AssetIndexDB, "_compute_key", return_value=old_key):
        AssetIndexDB.record(url, "audit", "A", tmp_path, path, 1)
    assert AssetIndexDB.query(url.lower()) is None


def test_incomplete_gallery_returns_partial_with_missing_asset(tmp_path):
    driver = StubDriver([asset("good.txt", b"A"), TargetAsset("file:///missing-audit-file", "second.txt", "extra")])
    result = run(driver, tmp_path)
    assert result["status"] == "partial"
    assert result["warnings"][0]["asset"] == "second.txt"


def test_notion_failure_preserves_primary_and_reports_reason(tmp_path):
    result = run(StubDriver([asset("good.txt", b"A")]), tmp_path, notion=True)
    assert result["status"] == "partial"
    assert Path(result["primary_asset"]).read_bytes() == b"A"
    assert "not configured" in result["operations"]["notion"]["reason"]


def test_transcription_failure_is_partial_with_actual_reason(tmp_path, media_samples):
    driver = StubDriver([asset("audio.mp3", media_samples[".mp3"])])
    with patch("cli.CloudTranscriber.transcribe", side_effect=DAError("Transcription API returned HTTP 429")):
        result = run(driver, tmp_path, transcribe=True)
    assert result["status"] == "partial"
    assert "429" in result["operations"]["transcription"]["reason"]
    assert Path(result["primary_asset"]).exists()


def test_local_audio_preflight_does_not_transcode_or_create_outputs(tmp_path):
    from drivers.audio.local_audio import LocalAudioDriver
    source = tmp_path / "speech.wav"
    source.write_bytes(b"local source")
    with patch("drivers.audio.local_audio.MusicUnlocker.transcode_to_mp3") as transcode:
        package = LocalAudioDriver().extract(str(source), inspect_only=True)
    transcode.assert_not_called()
    assert list(tmp_path.iterdir()) == [source]
    assert package.metadata["requires_processing"]


def test_unproven_416_response_never_promotes_partial_file(tmp_path):
    part = tmp_path / "asset.bin.part"
    part.write_bytes(b"bad")
    response = MagicMock(status_code=416, headers={"Content-Range": "bytes */100"})
    response.__enter__.return_value = response
    fetcher = Fetcher(FetcherOptions(max_retries=1))
    with patch("core.fetcher.requests.get", return_value=response), \
         patch.object(fetcher, "_download_via_curl", return_value=False), \
         patch("core.fetcher.time.sleep"):
        with pytest.raises(DownloadError):
            fetcher.download("https://example.invalid/asset", tmp_path / "asset.bin")
    assert not (tmp_path / "asset.bin").exists()


def test_obsidian_quoted_title_is_valid_yaml(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "note.md").write_text("body", encoding="utf-8")
    title = 'A "quoted" title\\path\nnext'
    note = VaultSync.sync_to_obsidian(assets, str(tmp_path / "vault"), title=title)
    assert yaml.safe_load(note.read_text(encoding="utf-8").split("---", 2)[1])["title"] == title


def test_partial_cli_exit_code_and_batch_counts():
    runner = CliRunner()
    partial = {"status": "partial", "warnings": [{"stage": "companion", "message": "missing"}]}
    with patch("cli.process_download", return_value=partial):
        single = runner.invoke(main, ["x", "--json"])
        batch = runner.invoke(main, ["x", "y", "--json"])
    assert single.exit_code == batch.exit_code == 2
    assert json.loads(single.output)["status"] == "partial"
    assert json.loads(batch.output)["success_count"] == 0
    assert json.loads(batch.output)["partial_count"] == 2


def test_skill_frontmatter_is_distributable():
    root = Path(__file__).resolve().parents[1]
    text = (root / "skills/download-anything/SKILL.md").read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(text.split("---", 2)[1])
    assert frontmatter["name"] == "download-anything"
    assert not any(char in frontmatter["description"] for char in "<>")
    assert "/Users/c.k/" not in text
    assert (root / "skills/download-anything/scripts/install.py").is_file()
