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


_TOKEN_RE = re.compile(r"\[pause(?::(\d+))?\]|\[breath\]", re.IGNORECASE)


def parse_script(text: str, default_pause_ms: int) -> list[tuple[str, object]]:
    """Split text on inline [pause] / [pause:Nms] / [breath] markers into an ordered
    list of ("speech", str), ("pause", ms), and ("breath", 0) parts. Markers are
    removed from the spoken text."""
    parts: list[tuple[str, object]] = []
    last = 0
    for m in _TOKEN_RE.finditer(text):
        seg = text[last:m.start()].strip()
        if seg:
            parts.append(("speech", seg))
        if m.group(0).lower().startswith("[breath"):
            parts.append(("breath", 0))
        else:
            parts.append(("pause", int(m.group(1)) if m.group(1) else default_pause_ms))
        last = m.end()
    tail = text[last:].strip()
    if tail:
        parts.append(("speech", tail))
    return parts


_PLOSIVES = set("pbtdkgc")


def starts_with_plosive(text: str) -> bool:
    for ch in text.lower():
        if ch.isalpha():
            return ch in _PLOSIVES
    return False


def plosive_pop(rng: np.random.Generator, sample_rate: int, level_db: float) -> np.ndarray:
    """A short low-frequency thump — the air-on-capsule pop of a plosive consonant."""
    n = int(sample_rate * 0.06)
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    idx = np.arange(n)
    freq = rng.uniform(80.0, 120.0)
    pop = np.sin(2 * np.pi * freq * idx / sample_rate) * np.exp(-idx / (sample_rate * 0.012))
    pop = pop / (np.max(np.abs(pop)) + 1e-9)
    return ((10.0 ** (level_db / 20.0)) * pop).astype(np.float32)


def add_plosive(mono: np.ndarray, rng: np.random.Generator, sample_rate: int, level_db: float) -> np.ndarray:
    """Mix a plosive pop in at the speech onset (where the consonant burst lands)."""
    if level_db <= -120 or mono.size == 0:
        return mono
    pop = plosive_pop(rng, sample_rate, level_db)
    onset = int(np.argmax(np.abs(mono) > 0.02))  # first audible sample
    out = mono.copy()
    end = min(onset + len(pop), len(out))
    out[onset:end] += pop[: end - onset]
    return out


def breath_sound(rng: np.random.Generator, sample_rate: int, level_db: float) -> np.ndarray:
    """A short, soft synthesized inhale (band-limited noise under an asymmetric
    envelope). A best-effort imitation — subtle by design."""
    n = int(sample_rate * 0.28)
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    noise = np.convolve(rng.standard_normal(n), np.ones(64) / 64, mode="same").astype(np.float32)
    t = np.linspace(0.0, 1.0, n)
    env = np.sqrt(t) * (1.0 - t) ** 1.2  # quick rise, slower fall = inhale shape
    breath = noise * (env / (env.max() + 1e-9))
    breath = breath / (np.max(np.abs(breath)) + 1e-9)
    return ((10.0 ** (level_db / 20.0)) * breath).astype(np.float32)


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
    sr = config.sample_rate

    def silence(ms: int) -> np.ndarray:
        return np.zeros(max(0, int(sr * ms / 1000)), dtype=np.float32)

    def render_speech(text: str, voice: str, fixed_speed: float | None) -> np.ndarray:
        # Synthesize each sentence separately so we (a) control the gap between them
        # and (b) vary the speaking pace per sentence — real speech speeds up and
        # slows down within a paragraph, it isn't uniform. A fixed_speed (per-line
        # override) pins the pace for deliberate emphasis instead of jittering it.
        sent_audios: list[np.ndarray] = []
        for sentence in split_sentences(text):
            speed = fixed_speed if fixed_speed is not None else config.speed * (1.0 + rng.uniform(-config.speed_jitter, config.speed_jitter))
            chunks = [
                np.asarray(r.audio, dtype=np.float32).reshape(-1)
                for r in model.generate(text=sentence, voice=voice, lang_code=config.lang_code, speed=speed)
            ]
            if chunks:
                sentence_audio = np.concatenate(chunks)
                if config.plosive_db > -120 and starts_with_plosive(sentence) and rng.random() < config.plosive_prob:
                    sentence_audio = add_plosive(sentence_audio, rng, sr, config.plosive_db)
                sent_audios.append(sentence_audio)
        gaps = [
            max(0, int(sr * rng.integers(config.sentence_pause_ms - 40, config.sentence_pause_ms + 41) / 1000))
            for _ in range(len(sent_audios) - 1)
        ]
        return assemble_audio(sent_audios, gaps) if sent_audios else np.zeros(0, dtype=np.float32)

    def render_part(kind: str, val: object, voice: str, fixed_speed: float | None) -> np.ndarray:
        if kind == "speech":
            return render_speech(str(val), voice, fixed_speed)
        if kind == "breath":
            return breath_sound(rng, sr, config.breath_db)
        return silence(int(val))  # pause

    turn_audios: list[np.ndarray] = []
    for turn in episode.turns:
        host = config.hosts[turn.speaker]
        # A turn is a sequence of speech segments, scripted [pause] beats, and [breath]s.
        segments = [
            render_part(kind, val, host.voice, turn.speed)
            for kind, val in parse_script(turn.text, config.beat_pause_ms)
        ]
        mono = np.concatenate(segments) if segments else np.zeros(0, dtype=np.float32)
        mono = apply_drift(mono, rng, config.drift_db)
        gain_db = turn.gain_db if turn.gain_db is not None else rng.uniform(-config.gain_jitter_db, config.gain_jitter_db)
        mono = apply_gain(mono, gain_db)
        turn_audios.append(pan_stereo(mono, host.pan))
    # Inter-turn gap: scripted pause_after if set, else random (negative = overlap).
    pauses = []
    for i in range(len(turn_audios) - 1):
        pa = episode.turns[i].pause_after
        ms = pa if pa is not None else int(rng.integers(config.pause_min_ms, config.pause_max_ms + 1))
        pauses.append(int(sr * ms / 1000))
    mix = add_room_tone(assemble_audio(turn_audios, pauses), rng, config.room_tone_db)
    return to_int16(mix)


def write_mp3(samples_int16: np.ndarray, sample_rate: int, mp3_path: str, tags: dict[str, str],
              mic_chain: bool = False, deess_intensity: float = 0.0, loudness_lufs: float | None = None) -> tuple[int, int]:
    """Write int16 samples (mono or stereo) to an MP3 with ID3 tags. With mic_chain,
    apply the physical-mic tone chain plus a real-podcast mastering tail (de-ess +
    loudness normalization). Returns (duration_secs, size_bytes)."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    try:
        sf.write(wav_path, samples_int16, sample_rate, subtype="PCM_16")
        cmd = ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-b:a", "128k"]
        if mic_chain:
            # Physical-mic chain: rumble filter, proximity body, gentle leveling,
            # presence lift + harmonic exciter to bring out consonant/plosive detail.
            filters = [
                "highpass=f=70",
                "bass=g=2:f=110",
                "acompressor=threshold=-20dB:ratio=2:attack=20:release=300",
                "treble=g=2.5:f=6500",
                "aexciter=amount=1.2:drive=5:freq=7000:blend=1",
            ]
            # Mastering tail, as a real podcast would: de-ess the sibilance the
            # presence/exciter adds, then normalize to broadcast loudness + true-peak.
            if deess_intensity > 0:
                filters.append(f"deesser=i={deess_intensity}:m=0.5:f=0.5:s=o")
            if loudness_lufs is not None and loudness_lufs > -70:
                filters.append(f"loudnorm=I={loudness_lufs}:TP=-1.5:LRA=11")
            cmd += ["-af", ",".join(filters)]
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
