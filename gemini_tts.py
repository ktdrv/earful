"""Gemini TTS engine: renders an Episode in Gemini's native two-speaker mode.

The alternative to tts.py (Kokoro). Gemini voices both hosts in one request and handles pacing,
turn-taking and pronunciation itself, so none of Kokoro's post-processing applies here. It reads
each turn's script text as written (Turn.raw) and maps the script's stage directions onto
Gemini's own inline tags.
"""
import base64
import http.client
import io
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
import wave
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from config import Config
from episode import Episode, Turn

API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
SAMPLE_RATE = 24000  # Gemini TTS returns 24 kHz mono 16-bit PCM
# One request's audio is capped at 16,384 output tokens, about 8.5 minutes at the ~32 tokens/s
# we measured. ~800 words is ~4.5 minutes of dense dialogue, well under the cap.
CHUNK_WORDS = 800
CHUNK_GAP_MS = 250  # silence where two chunks meet; always a turn boundary, so it reads as a normal gap
# A render outside this speaking rate didn't say what it was given: too fast means it skipped
# text, too slow means it padded or rambled. Measured renders run 164-180 wpm.
MIN_WPM, MAX_WPM = 110, 240
ATTEMPTS = 3

_OVERRIDE_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")  # [word](/ipa/), a Kokoro pronunciation override
_PAREN_RE = re.compile(r"\(([^)]*)\)")
_LEADING_PAREN_RE = re.compile(r"^\(([^)]*)\)\s*")
_TAG_RE = re.compile(r"<[^>]*>")
_PACE_STYLES = {"faster": "speaking rapidly", "slower": "speaking slowly"}
# Gemini's inline vocal-event tags (the list in its speech-generation docs).
_VOCAL_TAGS = {
    "argh", "breath", "heavy breath", "exhales", "cackle", "cheer", "chuckle", "chuckles", "cough",
    "cry", "gasp", "giggle", "groan", "growl", "grunt", "grr", "hiss", "laugh", "laughter", "moan",
    "pant", "pff", "phew", "scream", "shout", "shriek", "sigh", "sighs", "sneeze", "snicker", "snort",
    "sob", "throat-clearing", "tsk", "whimper", "whispers", "whispering", "yawn",
}
_TAG_ALIASES = {"laughs": "laugh", "beat": "short pause", "pause": "short pause"}


def _paren_to_tag(inner: str) -> str | None:
    """Map a script parenthetical to a Gemini inline tag, or None if it isn't one."""
    s = inner.strip().lower()
    s = _TAG_ALIASES.get(s, s)
    if s in _VOCAL_TAGS or s in ("short pause", "long pause"):
        return f"<{s}>"
    m = re.fullmatch(r"pause:\s*(\d+)", s)
    if m:
        return "<long pause>" if int(m.group(1)) >= 800 else "<short pause>"
    return None


def to_gemini(raw: str) -> tuple[str, str | None]:
    """Translate one turn as written into (text with Gemini inline tags, turn style).
    A leading parenthetical that isn't a tag directs the whole turn: (faster)/(slower) set the
    pace, anything else, like (dryly), passes through as the style. Other parentheticals become
    tags if they name one and are dropped otherwise. Dashes and ellipses stay; Gemini reads them
    as interruptions and hesitation."""
    raw = _OVERRIDE_RE.sub(r"\1", raw.strip())  # Gemini gets pronunciation from context; keep the word
    style = None
    m = _LEADING_PAREN_RE.match(raw)
    if m and _paren_to_tag(m.group(1)) is None:
        style = _PACE_STYLES.get(m.group(1).strip().lower(), m.group(1).strip()) or None
        raw = raw[m.end():]
    raw = _PAREN_RE.sub(lambda mt: _paren_to_tag(mt.group(1)) or "", raw)
    return re.sub(r"[ \t]+", " ", raw).strip(), style


def chunk_turns(turns: list[Turn], max_words: int) -> list[list[Turn]]:
    """Split consecutive turns into the fewest chunks of about max_words, all about the same size.
    Balanced rather than greedy: a greedy split can leave a two-word final chunk, whose padding
    alone would fail the speaking-rate check. A chunk can exceed max_words by half a turn."""
    sizes = [len(t.raw.split()) for t in turns]
    n = max(1, math.ceil(sum(sizes) / max_words))
    target = max(1, sum(sizes)) / n
    chunks: list[list[Turn]] = [[] for _ in range(n)]
    done = 0
    for t, size in zip(turns, sizes):
        # Each turn goes to the chunk its midpoint falls in.
        chunks[min(n - 1, int((done + size / 2) / target))].append(t)
        done += size
    return [c for c in chunks if c]


def request_body(turns: list[Turn], config: Config) -> dict:
    """A two-speaker 'conversational' request: each turn is its own text item tagged with the host's name."""
    items = []
    for t in turns:
        text, style = to_gemini(t.raw)
        if not text:
            continue
        meta = {"type": "speech_metadata", "speaker": config.hosts[t.speaker].name}
        if style:
            meta["style"] = style
        items.append({"type": "text", "text": text, "annotations": [meta]})
    return {
        "model": config.gemini_model,
        "input": [{"type": "user_input", "content": items}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": {
            "mode": "conversational",
            "speakers": [{"speaker": h.name, "voice": h.gemini_voice} for h in config.hosts.values()],
        }},
    }


def render_chunk(turns: list[Turn], config: Config, api_key: str) -> bytes:
    """Render one chunk to raw PCM, retrying transient API errors and audio whose length doesn't fit the text."""
    body = request_body(turns, config)
    words = sum(len(_TAG_RE.sub("", item["text"]).split()) for item in body["input"][0]["content"])
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode(),
                                 headers={"x-goog-api-key": api_key, "Content-Type": "application/json"})
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                resp = json.load(r)
            audio = [c for s in resp.get("steps", []) for c in s.get("content", []) if c.get("type") == "audio"]
            if not audio:
                raise RuntimeError(f"no audio in response: {json.dumps(resp)[:500]}")
            with wave.open(io.BytesIO(base64.b64decode(audio[-1]["data"]))) as w:
                fmt = (w.getframerate(), w.getnchannels(), w.getsampwidth())
                if fmt != (SAMPLE_RATE, 1, 2):
                    raise RuntimeError(f"expected {SAMPLE_RATE} Hz mono 16-bit audio, got {fmt}")
                pcm = w.readframes(w.getnframes())
            wpm = words / (len(pcm) / 2 / SAMPLE_RATE / 60)
            # Under ~50 words the fixed padding around the speech skews the rate too much to judge.
            if words >= 50 and not MIN_WPM <= wpm <= MAX_WPM:
                raise RuntimeError(f"{words} words came back at {wpm:.0f} wpm; the audio doesn't match the text")
            return pcm
        except urllib.error.HTTPError as e:
            # A 4xx other than rate limiting is a bad request or key; retrying won't fix it.
            if e.code != 429 and e.code < 500:
                raise RuntimeError(f"Gemini TTS HTTP {e.code}: {e.read().decode(errors='replace')[:800]}") from e
            err: Exception = e
        # OSError covers URLError, timeouts and dropped connections; HTTPException covers a response
        # cut off mid-read; ValueError and wave.Error cover a garbled body (bad JSON, base64 or WAV).
        except (OSError, http.client.HTTPException, ValueError, wave.Error, RuntimeError) as e:
            err = e
        if attempt == ATTEMPTS:
            raise RuntimeError(f"Gemini TTS failed after {ATTEMPTS} attempts: {err}") from err
        time.sleep(15 * attempt)  # long enough to clear a per-minute rate limit by the last try
    raise AssertionError("unreachable")


def synthesize(episode: Episode, config: Config) -> np.ndarray:
    """Render an Episode to a mono int16 array at SAMPLE_RATE. Chunks render in parallel."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing required env var: GEMINI_API_KEY (set it in .env)")
    missing = [hid for hid, h in config.hosts.items() if not h.gemini_voice]
    if missing:
        raise RuntimeError(f"Set gemini_voice for hosts {missing} in config.toml")
    if config.sample_rate != SAMPLE_RATE:
        raise RuntimeError(f"Gemini renders at {SAMPLE_RATE} Hz; set [tts] sample_rate = {SAMPLE_RATE}")
    chunks = chunk_turns(episode.turns, CHUNK_WORDS)
    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        pcms = list(pool.map(lambda c: render_chunk(c, config, api_key), chunks))
    gap = b"\x00\x00" * (SAMPLE_RATE * CHUNK_GAP_MS // 1000)
    return np.frombuffer(gap.join(pcms), dtype=np.int16)
