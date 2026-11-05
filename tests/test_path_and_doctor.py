"""
Unit tests for path_resolver and doctor
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.exceptions import DAError
from core.path_resolver import sanitize_filename, resolve_asset_path, resolve_output_directory, get_system_downloads_dir
from core.doctor import Doctor

def test_sanitize_filename():
    assert sanitize_filename("A/B\\C:D*E?F\"G<H>I|J") == "A_B_C_D_E_F_G_H_I_J"
    assert sanitize_filename("  Hello  World  ") == "Hello_World"
    assert sanitize_filename("") == "untitled_asset"
    long_name = "A" * 150
    assert len(sanitize_filename(long_name, max_length=50)) <= 50


@pytest.mark.parametrize("filename", ["../escape.txt", "..\\escape.txt", "/tmp/escape.txt", "C:/escape.txt"])
def test_resolve_asset_path_rejects_directory_escapes(tmp_path, filename):
    with pytest.raises(DAError, match="Unsafe asset filename"):
        resolve_asset_path(tmp_path, filename)


def test_resolve_asset_path_sanitizes_safe_relative_path(tmp_path):
    target = resolve_asset_path(tmp_path, "images/cover:01.jpg")
    assert target == tmp_path.resolve() / "images" / "cover_01.jpg"


def test_get_system_downloads_dir():
    p = get_system_downloads_dir()
    assert isinstance(p, Path)
    assert p.exists()

def test_resolve_output_directory():
    # Explicit path test
    p = resolve_output_directory("/tmp/custom_da", title="Test Asset", create_subfolder=False)
    assert p == Path("/tmp/custom_da").resolve()

    # With title
    p2 = resolve_output_directory("/tmp/custom_da", title="Test: Asset?", create_subfolder=True)
    assert p2.name.endswith("Test_Asset")

def test_doctor_check_all():
    report = Doctor.check_all()
    assert "python_version" in report
    assert report["python_version"]["ok"] is True
    assert "dependencies" in report
    assert "requests" in report["dependencies"]
    assert report["dependencies"]["requests"]["installed"] is True
    assert "curl" in report["external_tools"]
    assert "media_ready" in report


def test_doctor_scopes_ffmpeg_to_media_only(monkeypatch):
    def fake_which(tool):
        return None if tool in ("ffmpeg", "ffprobe") else "/usr/bin/" + tool

    monkeypatch.setattr("core.doctor.shutil.which", fake_which)
    report = Doctor.check_all()
    ffmpeg = report["external_tools"]["ffmpeg"]
    assert ffmpeg["installed"] is False
    assert ffmpeg["required"] is False
    assert ffmpeg["scope"] == "仅音视频"
    assert "文档" in ffmpeg["unaffected"]
    assert ffmpeg["install_hint"]
    assert report["media_ready"] is False
    # Missing FFmpeg must not mark text/document workloads as broken.
    assert report["all_required_ok"] is True


def test_doctor_media_ready_when_tools_are_present(monkeypatch):
    monkeypatch.setattr("core.doctor.shutil.which", lambda tool: "/usr/bin/" + tool)
    report = Doctor.check_all()
    assert report["media_ready"] is True


def test_auto_repair_switches_to_mirror_after_timeout(monkeypatch):
    report = {
        "dependencies": {
            "demo": {"installed": False, "pip_name": "demo", "required": True}
        }
    }
    monkeypatch.setattr(Doctor, "check_all", staticmethod(lambda: report))
    monkeypatch.setattr("core.doctor.shutil.which", lambda _tool: None)
    monkeypatch.delenv("DA_PIP_INDEX_URL", raising=False)
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(command, 1)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("core.doctor.subprocess.run", fake_run)
    assert Doctor.auto_repair() is True
    assert len(calls) == 2
    assert "--index-url" in calls[1]
    assert "pypi.tuna.tsinghua.edu.cn" in " ".join(calls[1])


def test_doctor_failure_lines_explain_missing_required_tool():
    import cli

    report = {
        "python_version": {"ok": True},
        "dependencies": {},
        "external_tools": {
            "curl": {"installed": False, "required": True},
            "ffmpeg": {"installed": False, "required": False},
        },
    }

    lines = cli._doctor_failure_lines(report)
    text = "\n".join(lines)

    assert "curl" in text
    assert "ffmpeg" not in text
    assert text.strip()
