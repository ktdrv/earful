import hashlib
import os
import random
import subprocess
import tempfile

import numpy as np
import soundfile as sf

from config import Config
from episode import Episode


def assemble_audio(turn_audios: list[np.ndarray], pauses: list[int]) -> np.ndarray:
    """Join per-turn audio with the gaps in `pauses` (one per boundary).
    A positive gap inserts silence; a negative gap overlaps the turns by that
    many samples (overlap-add), so hosts briefly talk over each other."""
    if not turn_audios:
        return np.zeros(0, dtype=np.float32)
    out = turn_audios[0].astype(np.float32).reshape(-1).copy()
    for i in range(1, len(turn_audios)):
        nxt = turn_audios[i].astype(np.float32).reshape(-1)
        gap = pauses[i - 1]
        if gap >= 0:
            out = np.concatenate([out, np.zeros(gap, dtype=np.float32), nxt])
        else:
            ov = min(-gap, len(out), len(nxt))
            if ov > 0:
                out[-ov:] = out[-ov:] + nxt[:ov]  # overlap-add the seam
                out = np.concatenate([out, nxt[ov:]])
            else:
                out = np.concatenate([out, nxt])
    return out


def to_int16(samples: np.ndarray) -> np.ndarray:
    clipped = np.clip(samples, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16)


def apply_gain(samples: np.ndarray, gain_db: float) -> np.ndarray:
    """Scale samples by a decibel offset (negative = quieter)."""
    return (samples.astype(np.float32) * (10.0 ** (gain_db / 20.0))).astype(np.float32)


def _episode_seed(episode: Episode) -> int:
    """Stable seed from episode content: organic within an episode, reproducible
    across runs (so the same script yields the same audio and GUID)."""
    h = hashlib.sha256(episode.title.encode())
    for t in episode.turns:
        h.update(t.speaker.encode())
        h.update(t.text.encode())
    return int.from_bytes(h.digest()[:8], "big")


def synthesize(episode: Episode, config: Config) -> np.ndarray:
    """Render an Episode to a mono int16 numpy array at config.sample_rate, with
    subtle per-turn variation (speed, level, pause length) for an organic feel."""
    from mlx_audio.tts.utils import load_model

    model = load_model(config.tts_model)
    rng = random.Random(_episode_seed(episode))
    turn_audios: list[np.ndarray] = []
    for turn in episode.turns:
        voice = config.voices[turn.speaker]
        speed = config.speed * (1.0 + rng.uniform(-config.speed_jitter, config.speed_jitter))
        chunks = [
            np.asarray(r.audio, dtype=np.float32).reshape(-1)
            for r in model.generate(text=turn.text, voice=voice, lang_code=config.lang_code, speed=speed)
        ]
        audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        gain_db = rng.uniform(-config.gain_jitter_db, config.gain_jitter_db)
        turn_audios.append(apply_gain(audio, gain_db))
    pauses = [
        int(config.sample_rate * rng.randint(config.pause_min_ms, config.pause_max_ms) / 1000)
        for _ in range(len(turn_audios) - 1)
    ]
    return to_int16(assemble_audio(turn_audios, pauses))


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
