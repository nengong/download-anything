"""
Lightweight Cloud Speech-to-Text Transcription Hook
Zero heavy local models. Leverages Groq, OpenAI, or SiliconFlow Whisper APIs
to transcribe audio/video speeches into high-density Markdown transcripts in seconds.
"""
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import requests

class CloudTranscriber:
    """Ultra-lightweight audio transcription connector without local GPU/CPU model bloat."""

    @classmethod
    def get_available_backend(cls) -> Optional[Tuple[str, str, str]]:
        """
        Returns (backend_name, api_key, api_endpoint, model_name).
        """
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            return ("Groq Whisper (Turbo)", groq_key, "https://api.groq.com/openai/v1/audio/transcriptions", "whisper-large-v3-turbo")

        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            return ("OpenAI Whisper", openai_key, "https://api.openai.com/v1/audio/transcriptions", "whisper-1")

        silicon_key = os.getenv("SILICONFLOW_KEY") or os.getenv("SILICON_FLOW_KEY")
        if silicon_key:
            return ("SiliconFlow Whisper", silicon_key, "https://api.siliconflow.cn/v1/audio/transcriptions", "FunAudioLLM/SenseVoiceSmall")

        return None

    @classmethod
    def transcribe(
        cls,
        audio_path: Path,
        output_dir: Path,
        title: str = "Audio_Transcript"
    ) -> Optional[Path]:
        """
        Transcribes audio file to timestamped Markdown transcript.
        Automatically compresses audio under 25MB if needed.
        """
        backend = cls.get_available_backend()
        if not backend:
            return None

        backend_name, api_key, endpoint, model_name = backend

        if not audio_path.exists() or audio_path.stat().st_size < 1000:
            return None

        # 1. Compress to 64k mono mp3 if larger than 24MB (API file size limit)
        upload_file = audio_path
        temp_compressed = None
        if audio_path.stat().st_size > 24 * 1024 * 1024:
            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg:
                temp_compressed = output_dir / f"temp_transcribe_{audio_path.stem}.mp3"
                cmd = [
                    ffmpeg, "-y", "-i", str(audio_path),
                    "-vn", "-ac", "1", "-b:a", "64k", str(temp_compressed)
                ]
                try:
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=True)
                    if temp_compressed.exists():
                        upload_file = temp_compressed
                except Exception:
                    pass

        # 2. Call Speech-to-Text API
        transcript_text = ""
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            with open(upload_file, "rb") as f:
                files = {
                    "file": (upload_file.name, f, "audio/mpeg")
                }
                data = {
                    "model": model_name,
                    "response_format": "verbose_json"
                }
                resp = requests.post(endpoint, headers=headers, files=files, data=data, timeout=120)
                if resp.status_code == 200:
                    res_json = resp.json()
                    segments = res_json.get("segments", [])
                    if segments:
                        lines = []
                        for seg in segments:
                            start = int(seg.get("start", 0))
                            mins, secs = divmod(start, 60)
                            hrs, mins = divmod(mins, 60)
                            time_str = f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs > 0 else f"{mins:02d}:{secs:02d}"
                            text = seg.get("text", "").strip()
                            lines.append(f"- **`[{time_str}]`** {text}")
                        transcript_text = "\n".join(lines)
                    else:
                        transcript_text = res_json.get("text", "")
        except Exception:
            pass
        finally:
            if temp_compressed and temp_compressed.exists():
                temp_compressed.unlink(missing_ok=True)

        if not transcript_text:
            return None

        # 3. Format and save [title].transcript.md
        transcript_file = output_dir / f"{title}.transcript.md"
        content = (
            f"# 🎙️ 语音文字稿: {title}\n\n"
            f"> - **转写引擎**: `{backend_name}` (`{model_name}`)\n"
            f"> - **原始音频**: `{audio_path.name}`\n\n"
            f"---\n\n"
            f"### 逐段转写与时间戳索引\n\n"
            f"{transcript_text}\n"
        )
        transcript_file.write_text(content, encoding="utf-8")
        return transcript_file
