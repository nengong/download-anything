"""
Unit tests verifying audit remediations:
- CLI doctor --fix and --json flags handling
- CLI login --json pure json mode
- Credentials file safe 0600 permissions & SQLite immutable mode
- Feishu and Notion AuthenticationRequiredError handling
"""
import os
import stat
import tempfile
import json
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml
from click.testing import CliRunner

from cli import main
from core.credentials import CredentialsManager
from core.doctor import Doctor
from core.exceptions import AuthenticationRequiredError
from drivers.docs.feishu import FeishuDocDriver
from drivers.docs.notion import NotionPublicDriver

def test_cli_doctor_fix_option():
    runner = CliRunner()
    result = runner.invoke(main, ["doctor", "--fix"])
    assert result.exit_code == 0
    assert "环境与依赖诊断报告" in result.output

def test_cli_doctor_json_option():
    runner = CliRunner()
    result = runner.invoke(main, ["doctor", "--json"])
    assert result.exit_code == 0
    assert '"python_version":' in result.output
    assert '"all_required_ok":' in result.output

def test_cli_login_json_option():
    runner = CliRunner()
    with patch("core.credentials.credentials_manager._harvest_from_browsers", return_value="test_cookie=123"), \
         patch("core.credentials.credentials_manager.save_credential") as save:
        result = runner.invoke(main, ["login", "quark", "--json"])
        assert result.exit_code == 0
        assert '"status": "success"' in result.output
        assert '"platform": "quark"' in result.output
        save.assert_called_once_with("quark", "test_cookie=123")

def test_credentials_safe_0600_permissions():
    with tempfile.TemporaryDirectory() as td:
        cfg_dir = Path(td)
        mgr = CredentialsManager(config_dir=cfg_dir)
        mgr.save_credential("baidu", "BDUSS=secret_token", section="pan")

        cred_file = cfg_dir / "credentials.yaml"
        assert cred_file.exists()
        file_mode = stat.S_IMODE(os.stat(cred_file).st_mode)
        # Should be strictly 0600 (-rw-------)
        assert file_mode == 0o600

def test_feishu_authentication_required_error():
    driver = FeishuDocDriver()
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.url = "https://feishu.cn/docx/private_doc"
    mock_resp.text = "Forbidden"

    with patch("requests.Session.get", return_value=mock_resp):
        with pytest.raises(AuthenticationRequiredError):
            driver.extract("https://feishu.cn/docx/private_doc")

def test_notion_authentication_required_error():
    driver = NotionPublicDriver()
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.url = "https://notion.so/login"
    mock_resp.text = "Login Required"

    with patch("requests.Session.get", return_value=mock_resp):
        with pytest.raises(AuthenticationRequiredError):
            driver.extract("https://username.notion.site/private-page")


def test_notion_public_url_containing_login_is_allowed():
    driver = NotionPublicDriver()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = "https://username.notion.site/login-guide"
    mock_resp.text = "<html><head><title>Public guide</title></head><body><p>Guide</p></body></html>"
    mock_resp.headers = {}

    with patch("requests.Session.get", return_value=mock_resp):
        package = driver.extract("https://username.notion.site/login-guide")
    assert package.title == "Public guide"


def test_cli_login_json_failure_returns_nonzero():
    runner = CliRunner()
    with patch("core.credentials.credentials_manager._harvest_from_browsers", return_value=None), \
         patch("core.credentials.credentials_manager._harvest_from_desktop_apps", return_value=None), \
         patch("cli.shutil.which", return_value=None), \
         patch.dict(os.environ, {"DA_GRAB_COOKIE_BIN": ""}):
        result = runner.invoke(main, ["login", "quark", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.output)["status"] == "error"


def test_cli_login_rejects_failed_grab_cookie_process():
    runner = CliRunner()
    with patch("core.credentials.credentials_manager._harvest_from_browsers", return_value=None), \
         patch("core.credentials.credentials_manager._harvest_from_desktop_apps", return_value=None), \
         patch("cli.shutil.which", return_value="/fake/grab-cookie"), \
         patch("cli.os.path.exists", return_value=True), \
         patch("cli.subprocess.run", return_value=MagicMock(returncode=2)):
        result = runner.invoke(main, ["login", "quark", "--json"])
    assert result.exit_code == 1
    assert "code 2" in json.loads(result.output)["message"]


def test_cli_rejects_unknown_options_without_starting_download():
    runner = CliRunner()
    with patch("cli.process_download") as process:
        result = runner.invoke(main, ["--jsonx", "https://example.com/asset"])
    assert result.exit_code != 0
    process.assert_not_called()


def test_cli_doctor_fix_json_requests_captured_installer_output():
    runner = CliRunner()
    with patch("core.doctor.Doctor.auto_repair", return_value=True) as repair:
        result = runner.invoke(main, ["doctor", "--json", "--fix"])
    assert result.exit_code == 0
    assert json.loads(result.output)["all_required_ok"] is True
    repair.assert_called_once_with(capture_output=True)


def test_doctor_auto_repair_captures_subprocess_output_when_requested():
    report = {"dependencies": {"requests": {"installed": False, "pip_name": "requests"}}}
    with patch("core.doctor.Doctor.check_all", return_value=report), \
         patch("core.doctor.shutil.which", return_value=None), \
         patch("core.doctor.subprocess.run", return_value=MagicMock(returncode=0)) as run:
        assert Doctor.auto_repair(capture_output=True) is True
    options = run.call_args.kwargs
    assert options["stdout"] == subprocess.PIPE
    assert options["stderr"] == subprocess.PIPE


def test_credentials_failed_write_preserves_existing_file():
    with tempfile.TemporaryDirectory() as td:
        cfg_dir = Path(td)
        mgr = CredentialsManager(config_dir=cfg_dir)
        mgr.save_credential("baidu", "BDUSS=original", section="pan")
        cred_file = cfg_dir / "credentials.yaml"
        original = cred_file.read_text(encoding="utf-8")

        with patch("yaml.safe_dump", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                mgr.save_credential("quark", "new_cookie", section="pan")

        assert cred_file.read_text(encoding="utf-8") == original
        assert list(cfg_dir.glob(".credentials.*.tmp")) == []


def test_credentials_save_reloads_stale_manager_cache():
    with tempfile.TemporaryDirectory() as td:
        cfg_dir = Path(td)
        first = CredentialsManager(config_dir=cfg_dir)
        second = CredentialsManager(config_dir=cfg_dir)
        first.save_credential("baidu", "baidu_cookie")
        second._load_yaml()
        first.save_credential("quark", "quark_cookie")
        second.save_credential("weibo", "weibo_cookie", section="social")

        data = yaml.safe_load((cfg_dir / "credentials.yaml").read_text(encoding="utf-8"))
        assert data["pan"]["baidu"]["cookie"] == "baidu_cookie"
        assert data["pan"]["quark"]["cookie"] == "quark_cookie"
        assert data["social"]["weibo"]["cookie"] == "weibo_cookie"


def test_quark_cookie_read_includes_committed_wal_updates():
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        db_path = home / "Library/Application Support/quark-cloud-drive/Cookies"
        db_path.parent.mkdir(parents=True)
        writer = sqlite3.connect(db_path)
        try:
            writer.execute("CREATE TABLE cookies (name TEXT, host_key TEXT, value TEXT)")
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("INSERT INTO cookies VALUES ('old', '.quark.cn', '1')")
            writer.commit()
            writer.execute("INSERT INTO cookies VALUES ('fresh', '.quark.cn', '2')")
            writer.commit()

            with patch("core.credentials.Path.home", return_value=home), \
                 patch("core.credentials.subprocess.run", return_value=MagicMock(returncode=1, stdout="")):
                cookie = CredentialsManager()._harvest_from_desktop_apps("quark")
            assert cookie is not None
            assert "fresh=2" in cookie
        finally:
            writer.close()
