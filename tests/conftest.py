"""Tiny real media fixtures so success tests exercise parseable containers."""
import shutil
import subprocess

import pytest


@pytest.fixture(scope="session")
def media_samples(tmp_path_factory):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg and ffprobe are required for real-media integration tests")
    root = tmp_path_factory.mktemp("media")
    samples = {}
    for ext, codec in [("m4a", "aac"), ("webm", "libopus"), ("ogg", "libvorbis"),
                       ("flac", "flac"), ("wav", "pcm_s16le"), ("mp3", "libmp3lame")]:
        path = root / f"sample.{ext}"
        subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=0.3", "-c:a", codec, str(path)], check=True)
        samples["." + ext] = path.read_bytes()
    video = root / "sample.mp4"
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i",
                    "color=black:size=32x32:duration=0.3", "-c:v", "mpeg4", str(video)], check=True)
    samples[".mp4"] = video.read_bytes()
    return samples
