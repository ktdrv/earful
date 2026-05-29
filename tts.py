import hashlib
import os
import re
import subprocess
import tempfile

import numpy as np
import soundfile as sf

from config import Config
from episode import Episode


def split_sentences(text: str) -> list[str]:
    """Split a turn into sentences at . ! ? boundaries (keeping the punctuation).
    Won't split inside 'A.I.' or numbers since those periods aren't followed by space."""
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def assemble_audio(turn_audios: list[np.ndarray], pauses: list[int]) -> np.ndarray:
    """Join per-turn audio with the gaps in `pauses` (one per boundary, in samples).
    A positive gap inserts silence; a negative gap overlaps the turns by that many
    samples (overlap-add). Works for mono (N,) or stereo (N, C) arrays."""
    if not turn_audios:
        return np.zeros(0, dtype=np.float32)
    out = turn_audios[0].astype(np.float32).copy()
    tail = out.shape[1:]  # () mono, (C,) stereo
    for i in range(1, len(turn_audios)):
        nxt = turn_audios[i].astype(np.float32)
        gap = pauses[i - 1]
        if gap >= 0:
            out = np.concatenate([out, np.zeros((gap, *tail), dtype=np.float32), nxt])
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


def apply_drift(mono: np.ndarray, rng: np.random.Generator, max_db: float) -> np.ndarray:
    """Multiply by a smooth low-frequency gain envelope (+/- max_db) so the level
    drifts slowly across the turn, mimicking a host shifting toward/away from the mic."""
    if max_db <= 0 or len(mono) < 2:
        return mono.astype(np.float32)
    ctrl = rng.uniform(-max_db, max_db, size=4)
    env_db = np.interp(np.arange(len(mono)), np.linspace(0, len(mono) - 1, len(ctrl)), ctrl)
    return (mono * (10.0 ** (env_db / 20.0))).astype(np.float32)


def pan_stereo(mono: np.ndarray, position: float) -> np.ndarray:
    """Constant-power pan of a mono signal to stereo. position in [-1, 1]."""
    angle = (float(np.clip(position, -1.0, 1.0)) + 1.0) * (np.pi / 4.0)
    return np.stack([mono * np.cos(angle), mono * np.sin(angle)], axis=1).astype(np.float32)


def add_room_tone(stereo: np.ndarray, rng: np.random.Generator, level_db: float) -> np.ndarray:
    """Mix in faint pink noise so it reads as a real recording, not a silent studio."""
    if level_db <= -120 or len(stereo) == 0:
        return stereo
    n = len(stereo)
    amp = 10.0 ** (level_db / 20.0)
    out = stereo.copy()
    for ch in range(stereo.shape[1]):
        white = rng.standard_normal(n)
        spec = np.fft.rfft(white)
        f = np.arange(len(spec))
        f[0] = 1
        pink = np.fft.irfft(spec / np.sqrt(f), n)
        pink = pink / (np.max(np.abs(pink)) + 1e-9)
        out[:, ch] += (amp * pink).astype(np.float32)
    return out.astype(np.float32)


def _episode_seed(episode: Episode) -> int:
    """Stable seed from episode content: organic within an episode, reproducible
    across runs (so the same script yields the same audio and GUID)."""
    h = hashlib.sha256(episode.title.encode())
    for t in episode.turns:
        h.update(t.speaker.encode())
        h.update(t.text.encode())
    return int.from_bytes(h.digest()[:8], "big")


def synthesize(episode: Episode, config: Config) -> np.ndarray:
    """Render an Episode to a stereo int16 numpy array at config.sample_rate, with
    subtle per-turn variation (speed, level, intra-turn drift, pan, pause) plus a
    faint room-tone bed, for an organic feel."""
    from mlx_audio.tts.utils import load_model

    model = load_model(config.tts_model)
    rng = np.random.default_rng(_episode_seed(episode))
    turn_audios: list[np.ndarray] = []
    for turn in episode.turns:
        host = config.hosts[turn.speaker]
        speed = config.speed * (1.0 + rng.uniform(-config.speed_jitter, config.speed_jitter))
        # Synthesize each sentence separately so we control the pause between them —
        # Kokoro's own end-of-sentence gap is short and gets shrunk further by speed,
        # which made interjections ("Huh.") run into the next sentence.
        sentences = split_sentences(turn.text)
        sent_audios: list[np.ndarray] = []
        for sentence in sentences:
            chunks = [
                np.asarray(r.audio, dtype=np.float32).reshape(-1)
                for r in model.generate(text=sentence, voice=host.voice, lang_code=config.lang_code, speed=speed)
            ]
            if chunks:
                sent_audios.append(np.concatenate(chunks))
        gaps = [
            int(config.sample_rate * max(0, rng.integers(config.sentence_pause_ms - 40, config.sentence_pause_ms + 41)) / 1000)
            for _ in range(len(sent_audios) - 1)
        ]
        mono = assemble_audio(sent_audios, gaps) if sent_audios else np.zeros(0, dtype=np.float32)
        mono = apply_drift(mono, rng, config.drift_db)
        mono = apply_gain(mono, rng.uniform(-config.gain_jitter_db, config.gain_jitter_db))
        turn_audios.append(pan_stereo(mono, host.pan))
    pauses = [
        int(config.sample_rate * rng.integers(config.pause_min_ms, config.pause_max_ms + 1) / 1000)
        for _ in range(len(turn_audios) - 1)
    ]
    mix = add_room_tone(assemble_audio(turn_audios, pauses), rng, config.room_tone_db)
    return to_int16(mix)


def write_mp3(samples_int16: np.ndarray, sample_rate: int, mp3_path: str, tags: dict[str, str], mic_chain: bool = False) -> tuple[int, int]:
    """Write int16 samples (mono or stereo) to an MP3 with ID3 tags. With mic_chain,
    apply a gentle highpass + compression so it sounds recorded. Returns (secs, bytes)."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    try:
        sf.write(wav_path, samples_int16, sample_rate, subtype="PCM_16")
        cmd = ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-b:a", "128k"]
        if mic_chain:
            cmd += ["-af", "highpass=f=80,acompressor=threshold=-20dB:ratio=2:attack=20:release=300,treble=g=-1:f=10000"]
        for k, v in tags.items():
            cmd += ["-metadata", f"{k}={v}"]
        cmd.append(mp3_path)
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed (exit {proc.returncode}): {proc.stderr.decode(errors='replace')[-800:]}")
    finally:
        os.unlink(wav_path)
    duration = int(round(len(samples_int16) / sample_rate))
    return duration, os.path.getsize(mp3_path)
