"""
Unit Tests for Music Ecosystem:
- MusicUnlocker (NCM decryption, FFmpeg MP3 transcoding)
- NetEase Cloud Music Driver (API resolution, outer link, lyrics, metadata)
- Spotify & Apple Music Driver (SpotDL architecture, iTunes Lookup, Spotify oEmbed)
- Open Music Driver (Internet Archive Audio, SoundCloud, CC attribution)
- Local Audio Driver (NCM / FLAC unlock and normalization)
"""
import base64
import json
import struct
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from core.music_unlocker import MusicUnlocker
from drivers.audio.music_163 import NetEaseMusicDriver
from drivers.audio.spotify_apple import SpotifyAppleMusicDriver
from drivers.audio.open_music import OpenMusicDriver
from drivers.audio.local_audio import LocalAudioDriver

def _create_synthetic_ncm(out_path: Path):
    with open(out_path, "wb") as f:
        # Magic
        f.write(b"CTENFDAM")
        f.write(b"\x01\x70")
        
        # RC4 key
        raw_key = b"neteasecloudmusic" + b"test_secret_rc4_key"
        pad = 16 - (len(raw_key) % 16)
        raw_key += bytes([pad] * pad)
        cipher = Cipher(algorithms.AES(MusicUnlocker.NCM_CORE_KEY), modes.ECB())
        enc = cipher.encryptor()
        enc_key = bytearray(enc.update(raw_key) + enc.finalize())
        for i in range(len(enc_key)):
            enc_key[i] ^= 0x64
        f.write(struct.pack("<I", len(enc_key)))
        f.write(enc_key)
        
        # Meta
        meta_dict = {
            "musicName": "晴天 (Live)",
            "artist": [["周杰伦", 6452]],
            "album": "叶惠美",
            "format": "mp3"
        }
        b64_meta = base64.b64encode(json.dumps(meta_dict).encode("utf-8"))
        raw_meta = b"163 key(Don't modify):" + b64_meta
        pad2 = 16 - (len(raw_meta) % 16)
        raw_meta += bytes([pad2] * pad2)
        cipher2 = Cipher(algorithms.AES(MusicUnlocker.NCM_META_KEY), modes.ECB())
        enc2 = cipher2.encryptor()
        enc_meta = bytearray(enc2.update(raw_meta) + enc2.finalize())
        for i in range(len(enc_meta)):
            enc_meta[i] ^= 0x63
        f.write(struct.pack("<I", len(enc_meta)))
        f.write(enc_meta)
        
        # Gap & CRC
        f.write(b"\x00" * 9)
        # Img space & len
        f.write(struct.pack("<I", 0))
        f.write(struct.pack("<I", 0))
        
        # Audio stream
        f.write(b"\x42" * 512)

def test_music_unlocker_ncm_decrypt():
    with tempfile.TemporaryDirectory() as td:
        tpath = Path(td)
        ncm_file = tpath / "sample_track.ncm"
        _create_synthetic_ncm(ncm_file)
        
        assert MusicUnlocker.is_ncm(ncm_file)
        
        dest_dir = tpath / "unlocked"
        audio_path, cover_path, meta = MusicUnlocker.unlock_ncm(ncm_file, dest_dir=dest_dir)
        
        assert audio_path.exists()
        assert audio_path.name == "sample_track.mp3"
        assert meta.get("musicName") == "晴天 (Live)"
        assert meta.get("album") == "叶惠美"

def test_netease_driver_can_handle():
    driver = NetEaseMusicDriver()
    assert driver.can_handle("https://music.163.com/#/song?id=186016")
    assert driver.can_handle("https://music.163.com/song?id=33894312")
    assert driver.can_handle("http://163cn.tv/abcXYZ")
    assert not driver.can_handle("https://y.qq.com/n/ryqq/songDetail/1234")

def test_netease_driver_extract_mock(monkeypatch):
    driver = NetEaseMusicDriver()
    
    mock_detail = {
        "songs": [{
            "name": "稻香",
            "artists": [{"name": "周杰伦"}],
            "album": {"name": "魔杰座", "picUrl": "https://p1.music.126.net/cover.jpg"},
            "duration": 223000
        }]
    }
    mock_lyric = {
        "lrc": {"lyric": "[00:00.00] 对这个世界如果你有太多的抱怨\n[00:04.00] 跌倒了 就不敢继续往前走"}
    }
    
    def mock_get(self, url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "detail" in str(url):
            resp.json.return_value = mock_detail
        elif "lyric" in str(url):
            resp.json.return_value = mock_lyric
        return resp

    def mock_head(self, url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.url = "http://m10.music.126.net/daoxiang.mp3"
        resp.headers = {"Content-Length": "4500000"}
        return resp

    monkeypatch.setattr("requests.Session.get", mock_get)
    monkeypatch.setattr("requests.Session.head", mock_head)

    pkg = driver.extract("https://music.163.com/#/song?id=186016")
    assert pkg.platform == "music_163"
    assert "稻香" in pkg.title
    assert "周杰伦" in pkg.title
    assert pkg.primary_asset.filename == "content.mp3"
    assert pkg.primary_asset.url == "http://m10.music.126.net/daoxiang.mp3"
    assert "对这个世界如果你有太多的抱怨" in pkg.metadata["lyrics"]
    assert len(pkg.assets) == 2  # mp3 + cover

def test_spotify_apple_driver_can_handle():
    driver = SpotifyAppleMusicDriver()
    assert driver.can_handle("https://music.apple.com/us/album/after-hours/1499378108?i=1499378607")
    assert driver.can_handle("https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b")
    assert not driver.can_handle("https://music.163.com/song?id=123")

def test_spotify_apple_driver_apple_extract(monkeypatch):
    driver = SpotifyAppleMusicDriver()
    mock_itunes = {
        "results": [{
            "trackName": "Blinding Lights",
            "artistName": "The Weeknd",
            "collectionName": "After Hours",
            "trackTimeMillis": 200000,
            "artworkUrl100": "https://is1-ssl.mzstatic.com/image/thumb/100x100bb.jpg"
        }]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_itunes
    monkeypatch.setattr("requests.Session.get", lambda *args, **kwargs: mock_resp)
    monkeypatch.setattr(driver, "_find_audio_stream", lambda *args: ("https://stream.example.com/audio.mp3", 4000000))

    pkg = driver.extract("https://music.apple.com/us/album/after-hours/1499378108?i=1499378607")
    assert pkg.platform == "apple_music"
    assert "Blinding Lights" in pkg.title
    assert "3000x3000bb.jpg" in pkg.assets[1].url

def test_open_music_driver_archive_org(monkeypatch):
    driver = OpenMusicDriver()
    assert driver.can_handle("https://archive.org/details/beethoven_symphony_5")
    assert driver.can_handle("https://soundcloud.com/artist/sample-track")
    assert not driver.can_handle("https://music.163.com")

    mock_archive_data = {
        "metadata": {
            "title": "Symphony No. 5 in C Minor",
            "creator": "Ludwig van Beethoven",
            "licenseurl": "https://creativecommons.org/publicdomain/mark/1.0/"
        },
        "files": [
            {"name": "symphony5.mp3", "format": "VBR MP3", "size": "15000000"}
        ]
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_archive_data
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: mock_resp)

    pkg = driver.extract("https://archive.org/details/beethoven_symphony_5")
    assert pkg.platform == "open_music"
    assert "Symphony No. 5" in pkg.title
    assert "https://archive.org/download/beethoven_symphony_5/symphony5.mp3" in pkg.primary_asset.url
    assert "Ludwig van Beethoven" in pkg.metadata["creator"]

def test_local_audio_driver():
    driver = LocalAudioDriver()
    with tempfile.TemporaryDirectory() as td:
        tpath = Path(td)
        ncm_file = tpath / "my_track.ncm"
        _create_synthetic_ncm(ncm_file)
        
        assert driver.can_handle(str(ncm_file))
        pkg = driver.extract(str(ncm_file))
        assert pkg.platform == "local_audio"
        assert "晴天" in pkg.title
        assert pkg.primary_asset.filename == "my_track.mp3"
