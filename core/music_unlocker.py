"""
Music Unlocker and Universal Audio Transcoder Engine
Supports decrypting client-encrypted music formats (e.g. NetEase Cloud Music .ncm)
and transcoding diverse audio containers (FLAC, APE, WAV, OGG, M4A) into standard 320kbps MP3.
"""
import base64
import json
import os
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

class MusicUnlocker:
    """Decrypts proprietary music formats and standardizes audio to MP3."""

    NCM_CORE_KEY = b"hzHRAmso5kInbaxW"
    NCM_META_KEY = bytes([0x23, 0x31, 0x34, 0x6C, 0x6A, 0x6B, 0x5F, 0x21, 0x5C, 0x5D, 0x26, 0x30, 0x55, 0x3C, 0x27, 0x28])
    NCM_MAGIC = b"CTENFDAM"

    SUPPORTED_LOCAL_FORMATS = {".ncm", ".qmc0", ".qmc3", ".qmcflac", ".qmcogg", ".mflac", ".flac", ".ape", ".wav", ".ogg", ".opus", ".m4a", ".aac"}

    @classmethod
    def is_ncm(cls, file_path: Path) -> bool:
        if not file_path.exists() or file_path.is_dir():
            return False
        if file_path.suffix.lower() == ".ncm":
            return True
        try:
            with open(file_path, "rb") as f:
                return f.read(8) == cls.NCM_MAGIC
        except Exception:
            return False

    @classmethod
    def unlock_ncm(cls, ncm_path: Path, dest_dir: Optional[Path] = None) -> Tuple[Path, Optional[Path], Dict[str, Any]]:
        """
        Decrypt NetEase .ncm file to clean audio (.mp3 / .flac) and extract embedded cover image and metadata.
        Returns: (audio_path, cover_path, metadata)
        """
        if dest_dir is None:
            dest_dir = ncm_path.parent

        dest_dir.mkdir(parents=True, exist_ok=True)

        with open(ncm_path, "rb") as f:
            header = f.read(8)
            if header != cls.NCM_MAGIC:
                raise ValueError(f"File {ncm_path.name} is not a valid NCM encrypted file")

            f.seek(2, 1)  # Gap 2 bytes

            # 1. AES Core Key -> RC4 Key
            key_len = struct.unpack("<I", f.read(4))[0]
            key_data = bytearray(f.read(key_len))
            for i in range(len(key_data)):
                key_data[i] ^= 0x64

            decrypted_key = cls._aes_ecb_decrypt(cls.NCM_CORE_KEY, bytes(key_data))
            rc4_key = cls._pkcs7_unpad(decrypted_key)[17:]

            # 2. Metadata: XOR 0x63 -> skip 22-byte prefix -> base64 -> AES -> JSON
            meta_len = struct.unpack("<I", f.read(4))[0]
            metadata = {}
            if meta_len > 0:
                meta_data = bytearray(f.read(meta_len))
                for i in range(len(meta_data)):
                    meta_data[i] ^= 0x63
                meta_b64 = base64.b64decode(bytes(meta_data[22:]))
                decrypted_meta = cls._aes_ecb_decrypt(cls.NCM_META_KEY, meta_b64)
                meta_text = cls._pkcs7_unpad(decrypted_meta).decode("utf-8")
                try:
                    metadata = json.loads(meta_text[6:])
                except Exception:
                    metadata = {}

            # 3. Gap
            f.seek(5, 1)

            # 4. Album Cover Image
            img_space = struct.unpack("<I", f.read(4))[0]
            img_len = struct.unpack("<I", f.read(4))[0]
            cover_path = None
            if img_len > 0:
                img_data = f.read(img_len)
                cover_name = f"{ncm_path.stem}.cover.jpg"
                cover_path = dest_dir / cover_name
                with open(cover_path, "wb") as img_f:
                    img_f.write(img_data)
            if img_space > img_len:
                f.seek(img_space - img_len, 1)

            # 5. Build modified RC4 S-Box and repeating mask
            box = list(range(256))
            j = 0
            for i in range(256):
                j = (j + box[i] + rc4_key[i % len(rc4_key)]) & 0xff
                box[i], box[j] = box[j], box[i]

            mask_stream = bytes(
                box[(box[i] + box[(i + box[i]) & 0xff]) & 0xff] for i in range(256)
            )

            # 6. Decrypt Audio Stream
            audio_format = str(metadata.get("format", "mp3")).lower()
            if audio_format not in ("mp3", "flac"):
                audio_format = "mp3"

            audio_data = f.read()
            mask = (mask_stream * (len(audio_data) // 256 + 1))[1:1 + len(audio_data)]
            raw_audio_path = dest_dir / f"{ncm_path.stem}.{audio_format}"
            with open(raw_audio_path, "wb") as out_f:
                out_f.write(bytes(a ^ b for a, b in zip(audio_data, mask)))

        # 7. Embed cover/tags; standardize FLAC to MP3
        final_mp3_path = dest_dir / f"{ncm_path.stem}.mp3"
        tag_meta = {
            "title": metadata.get("musicName", ncm_path.stem),
            "artist": "/".join([a[0] for a in metadata.get("artist", [])]) if isinstance(metadata.get("artist"), list) else metadata.get("artist", ""),
            "album": metadata.get("album", ""),
        }
        if audio_format == "mp3":
            tagged_path = dest_dir / f"{ncm_path.stem}.tagged.mp3"
            if cls._embed_mp3_metadata(raw_audio_path, tagged_path, cover_path, tag_meta):
                raw_audio_path.unlink(missing_ok=True)
                tagged_path.replace(final_mp3_path)
                return final_mp3_path, cover_path, metadata
            return raw_audio_path, cover_path, metadata

        if cls.transcode_to_mp3(
            src_path=raw_audio_path,
            dest_path=final_mp3_path,
            cover_path=cover_path,
            metadata=tag_meta
        ):
            try:
                raw_audio_path.unlink(missing_ok=True)
            except Exception:
                pass
            return final_mp3_path, cover_path, metadata

        return raw_audio_path, cover_path, metadata

    @staticmethod
    def _aes_ecb_decrypt(key: bytes, data: bytes) -> bytes:
        cipher = Cipher(algorithms.AES(key), modes.ECB())
        decryptor = cipher.decryptor()
        return decryptor.update(data) + decryptor.finalize()

    @staticmethod
    def _pkcs7_unpad(data: bytes, block_size: int = 16) -> bytes:
        if not data:
            return data
        pad = data[-1]
        if 0 < pad <= block_size and data.endswith(bytes([pad]) * pad):
            return data[:-pad]
        return data

    @staticmethod
    def _embed_mp3_metadata(src_path: Path, dest_path: Path, cover_path: Optional[Path],
                            metadata: Dict[str, str]) -> bool:
        """Attach tags and cover to an existing MP3 without re-encoding the audio."""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return False

        cmd = [ffmpeg, "-y", "-i", str(src_path)]
        if cover_path and cover_path.exists():
            cmd.extend([
                "-i", str(cover_path),
                "-map", "0:a",
                "-map", "1:0",
                "-id3v2_version", "3",
                "-metadata:s:v", "title=Album cover",
                "-metadata:s:v", "comment=Cover (front)",
            ])
        else:
            cmd.extend(["-map", "0:a"])
        cmd.extend(["-c:a", "copy"])
        for key in ("title", "artist", "album"):
            if metadata.get(key):
                cmd.extend(["-metadata", f"{key}={metadata[key]}"])
        cmd.append(str(dest_path))

        try:
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
            return res.returncode == 0 and dest_path.exists() and dest_path.stat().st_size > 512
        except Exception:
            return False

    @classmethod
    def transcode_to_mp3(
        cls,
        src_path: Path,
        dest_path: Path,
        bitrate: str = "320k",
        cover_path: Optional[Path] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> bool:
        """Convert any audio file to standard 320kbps MP3 with embedded tags and cover art."""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return False

        cmd = [ffmpeg, "-y", "-i", str(src_path)]
        if cover_path and cover_path.exists():
            cmd.extend([
                "-i", str(cover_path),
                "-map", "0:a",
                "-map", "1:0",
                "-id3v2_version", "3",
                "-metadata:s:v", "title=Album cover",
                "-metadata:s:v", "comment=Cover (front)"
            ])
        else:
            cmd.extend(["-map", "0:a"])

        if metadata:
            if metadata.get("title"):
                cmd.extend(["-metadata", f"title={metadata['title']}"])
            if metadata.get("artist"):
                cmd.extend(["-metadata", f"artist={metadata['artist']}"])
            if metadata.get("album"):
                cmd.extend(["-metadata", f"album={metadata['album']}"])

        cmd.extend(["-codec:a", "libmp3lame", "-b:a", bitrate, str(dest_path)])

        try:
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
            return res.returncode == 0 and dest_path.exists() and dest_path.stat().st_size > 512
        except Exception:
            return False
