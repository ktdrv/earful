import os
import subprocess
import tempfile

import numpy as np
import soundfile as sf

from config import Config
from episode import Episode


def assemble_audio(turn_audios: list[np.ndarray], pause_samples: int) -> np.ndarray:
    if not turn_audios:
        return np.zeros(0, dtype=np.float32)
    silence = np.zeros(pause_samples, dtype=np.float32)
    parts: list[np.ndarray] = []
    for i, a in enumerate(turn_audios):
        parts.append(a.astype(np.float32).reshape(-1))
        if i < len(turn_audios) - 1:
            parts.append(silence)
    return np.concatenate(parts)


def to_int16(samples: np.ndarray) -> np.ndarray:
    clipped = np.clip(samples, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16)


def synthesize(episode: Episode, config: Config) -> np.ndarray:
    """Render an Episode to a mono int16 numpy array at config.sample_rate."""
    from mlx_audio.tts.utils import load_model

    model = load_model(config.tts_model)
    pause_samples = int(config.sample_rate * config.pause_ms / 1000)
    turn_audios: list[np.ndarray] = []
    for turn in episode.turns:
        voice = config.voices[turn.speaker]
        chunks = [
            np.asarray(r.audio, dtype=np.float32).reshape(-1)
            for r in model.generate(text=turn.text, voice=voice, lang_code=config.lang_code)
        ]
        turn_audios.append(np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32))
    return to_int16(assemble_audio(turn_audios, pause_samples))


def write_mp3(samples_int16: np.ndarray, sample_rate: int, mp3_path: str, tags: dict[str, str]) -> tuple[int, int]:
    """Write int16 samples to an MP3 with ID3 tags. Returns (duration_secs, size_bytes)."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    try:
        sf.write(wav_path, samples_int16, sample_rate, subtype="PCM_16")
        meta: list[str] = []
        for k, v in tags.items():
            meta += ["-metadata", f"{k}={v}"]
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-b:a", "128k", *meta, mp3_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed (exit {proc.returncode}): {proc.stderr.decode(errors='replace')[-800:]}")
    finally:
        os.unlink(wav_path)
    duration = int(round(len(samples_int16) / sample_rate))
    return duration, os.path.getsize(mp3_path)
