"""
Unit Tests for Resilient Streaming Fetcher
"""
import pytest
from core.fetcher import Fetcher, FetcherOptions
from core.exceptions import FileTooLargeError

def test_fetcher_pre_download_size_guard(tmp_path, monkeypatch):
    fetcher = Fetcher(FetcherOptions(max_bytes=1000))
    dest = tmp_path / "large.bin"

    class FakeResponse:
        status_code = 200
        headers = {"Content-Length": "2000"}
        def raise_for_status(self): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, chunk_size=65536):
            yield b"x" * 2000

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(FileTooLargeError) as exc_info:
        fetcher.download("https://example.com/test", dest)

    assert "exceeds maximum allowed limit" in str(exc_info.value)
    assert not dest.exists()


def test_fetcher_data_uri_size_guard(tmp_path):
    fetcher = Fetcher(FetcherOptions(max_bytes=10))
    dest = tmp_path / "large.txt"
    with pytest.raises(FileTooLargeError, match="exceeds maximum allowed limit"):
        fetcher.download("data:text/plain,12345678901", dest)
    assert not dest.exists()


def test_fetcher_file_uri_size_guard(tmp_path):
    fetcher = Fetcher(FetcherOptions(max_bytes=10))
    source = tmp_path / "source.txt"
    source.write_bytes(b"x" * 11)
    dest = tmp_path / "dest.txt"
    with pytest.raises(FileTooLargeError, match="exceeds maximum allowed limit"):
        fetcher.download(source.as_uri(), dest)
    assert not dest.exists()
    assert source.read_bytes() == b"x" * 11
