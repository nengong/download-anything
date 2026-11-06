"""Installer behavior that users hit before the CLI can start."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL_PATH = ROOT / "skills" / "download-anything" / "scripts" / "install.py"


def load_install_module():
    spec = importlib.util.spec_from_file_location("da_install", INSTALL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


install = load_install_module()


def test_installer_status_does_not_crash_on_legacy_console(tmp_path):
    script = '''
import importlib.util, sys
spec = importlib.util.spec_from_file_location("installer", sys.argv[1])
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
installer._find_compatible_python = lambda: ([sys.executable], (3, 12, 0))
installer._create_venv = lambda *args, **kwargs: False
sys.argv = [sys.argv[1], "--venv", sys.argv[2]]
try:
    installer.main()
except SystemExit:
    pass
'''
    result = subprocess.run(
        [sys.executable, "-c", script, str(INSTALL_PATH), str(tmp_path / "venv")],
        env={**os.environ, "PYTHONIOENCODING": "cp1252:strict"},
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert b"[install]" in result.stdout
    assert b"UnicodeEncodeError" not in result.stderr


def test_windows_launcher_is_used_without_managed_python_or_prompt(monkeypatch, tmp_path):
    from unittest.mock import Mock
    run, confirm = Mock(), Mock(return_value=False)
    monkeypatch.setattr(install.subprocess, "run", run)
    monkeypatch.setattr(install, "_confirm", confirm)
    assert install._create_venv(tmp_path / "venv", "uv.exe", ["py", "-3.11"])
    assert run.call_args.args[0] == ["py", "-3.11", "-m", "venv", str(tmp_path / "venv")]
    confirm.assert_not_called()


def test_existing_unseeded_environment_is_repaired_offline(tmp_path):
    import os
    import venv
    target = tmp_path / "unseeded"
    venv.EnvBuilder(with_pip=False).create(target)
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    assert subprocess.run([str(python), "-m", "pip", "--version"], capture_output=True).returncode != 0
    install._ensure_pip(python)
    assert subprocess.run([str(python), "-m", "pip", "--version"], capture_output=True).returncode == 0


def test_python_floor_is_310():
    assert install._supported((3, 9, 18)) is False
    assert install._supported((3, 10, 0)) is True
    assert install._supported((3, 12, 4)) is True
    assert install._supported(None) is False


def test_probe_python_reads_real_interpreter():
    assert install._probe_python([sys.executable]) == tuple(sys.version_info[:3])


def test_pip_sources_put_official_first_then_domestic(monkeypatch):
    monkeypatch.delenv("DA_PIP_INDEX_URL", raising=False)
    sources = install._pip_sources()
    assert sources[0] == ("官方 PyPI", None)
    urls = [url for _label, url in sources]
    assert any("pypi.tuna.tsinghua.edu.cn" in (url or "") for url in urls)
    assert any("mirrors.aliyun.com/pypi" in (url or "") for url in urls)


def test_pip_sources_honor_custom_index(monkeypatch):
    monkeypatch.setenv("DA_PIP_INDEX_URL", "https://example.com/simple")
    assert install._pip_sources()[0] == (
        "自定义源 DA_PIP_INDEX_URL",
        "https://example.com/simple",
    )


def test_install_switches_to_mirror_after_timeout(monkeypatch):
    monkeypatch.delenv("DA_PIP_INDEX_URL", raising=False)
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(command, 1)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(install.subprocess, "run", fake_run)
    ok = install._install_with_mirrors(
        ["python", "-m", "pip", "install"], ["download-anything"], True, "test"
    )
    assert ok is True
    assert len(calls) == 2
    assert "--index-url" in calls[1]
    assert "pypi.tuna.tsinghua.edu.cn" in " ".join(calls[1])


def test_uv_managed_python_retries_with_domestic_mirror(monkeypatch, tmp_path):
    monkeypatch.setattr(install, "_supported", lambda _version: False)
    monkeypatch.delenv("UV_PYTHON_INSTALL_MIRROR", raising=False)
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs.get("env")))
        if len(calls) == 1:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(install.subprocess, "run", fake_run)
    assert install._create_venv(tmp_path / "venv", "/fake/uv", None, auto_yes=True) is True
    assert len(calls) == 2
    assert "gh-proxy.com" in calls[1][1]["UV_PYTHON_INSTALL_MIRROR"]


def test_managed_python_download_requires_confirmation(monkeypatch, tmp_path):
    monkeypatch.setattr(install, "_supported", lambda _version: False)
    monkeypatch.setattr(install, "_confirm", lambda _question: False)
    calls = []
    monkeypatch.setattr(install.subprocess, "run", lambda *args, **kwargs: calls.append(args))

    assert install._create_venv(tmp_path / "venv", "/fake/uv", None) is False
    assert calls == []


def test_managed_python_download_skips_prompt_with_yes(monkeypatch, tmp_path):
    monkeypatch.setattr(install, "_supported", lambda _version: False)
    monkeypatch.setattr(install, "_confirm", lambda _question: (_ for _ in ()).throw(AssertionError("prompted")))
    calls = []
    monkeypatch.setattr(
        install.subprocess,
        "run",
        lambda command, **kwargs: calls.append(command) or subprocess.CompletedProcess(command, 0),
    )

    assert install._create_venv(tmp_path / "venv", "/fake/uv", None, auto_yes=True) is True
    assert calls and "--python" in calls[0]


def test_windows_guidance_uses_py_launcher(monkeypatch):
    monkeypatch.setattr(install.sys, "platform", "win32")
    guidance = install._python_guidance()
    assert "py -3.12" in guidance
    assert "winget install -e --id Python.Python.3.12" in guidance


def test_install_reports_failure_after_all_sources(monkeypatch):
    monkeypatch.delenv("DA_PIP_INDEX_URL", raising=False)
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(install.subprocess, "run", fake_run)
    ok = install._install_with_mirrors(
        ["python", "-m", "pip", "install"], ["download-anything"], True, "test"
    )
    assert ok is False
    assert len(calls) == 1 + len(install.PYPI_MIRRORS)
