"""
Unit tests for path_resolver and doctor
"""
import os
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
