# Earful Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local pipeline that turns an episode JSON (written by Claude) into a voiced MP3, uploads it to Cloudflare R2, and regenerates a standard podcast RSS feed any podcast app can subscribe to.

**Architecture:** Claude (in this directory) researches a topic and writes `episode.json`, then runs `python produce.py episode.json`. `produce.py` orchestrates four focused modules — `config` (settings), `tts` (Kokoro synthesis + MP3), `feed` (manifest + RSS), `storage` (R2) — and `episode` (the JSON model). The manifest (`episodes.json`) lives in R2 as the durable source of truth; the feed is regenerated from it every run.

**Tech Stack:** Python 3.14, mlx-audio (Kokoro-82M-bf16) for TTS, ffmpeg for MP3, soundfile + numpy for audio, boto3 for R2 (S3-compatible), Pillow for cover art, pytest for tests.

**Conventions:**
- All functions/methods get type hints (project rule).
- Blank lines contain zero whitespace (project rule).
- Run everything via the project venv: `.venv/bin/python`, `.venv/bin/pytest`.
- TDD: failing test → minimal code → green → commit. Pure logic is unit-tested; the real Kokoro model and live R2 are exercised by clearly-marked integration tests/steps.

---

## Task 1: Dependencies & skeleton

**Files:**
- Create: `requirements.txt`
- Create: `config.toml`
- Create: `tests/__init__.py` (empty)

- [ ] **Step 1: Write `requirements.txt`**

```
boto3
python-dotenv
numpy
soundfile
mlx-audio
pillow
pytest
```

- [ ] **Step 2: Install deps + system tools**

Run:
```bash
.venv/bin/pip install -r requirements.txt
brew install ffmpeg espeak-ng
```
Expected: pip finishes without error; `ffmpeg -version` and `espeak-ng --version` both print a version. espeak-ng is Kokoro's grapheme→phoneme backend and fails silently if missing.

- [ ] **Step 3: Write `config.toml`** (podcast metadata + voices; edit values to taste later)

```toml
[podcast]
title = "Earful"
description = "AI-produced episodes on whatever I want to learn next."
author = "Your Name"
email = "you@example.com"
language = "en-us"
explicit = false
category = "Education"
link = ""

[voices]
host_a = "am_michael"
host_b = "af_heart"

[tts]
model = "mlx-community/Kokoro-82M-bf16"
lang_code = "a"
pause_ms = 400
sample_rate = 24000
```

- [ ] **Step 4: Create empty `tests/__init__.py`**

```bash
touch tests/__init__.py
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt config.toml tests/__init__.py
git commit -m "feat: project deps and config"
```

---

## Task 2: Config loading (`config.py`)

**Files:**
- Create: `config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
import os
import textwrap
import config as cfg


def test_load_config_reads_toml_and_env(tmp_path, monkeypatch):
    toml = tmp_path / "config.toml"
    toml.write_text(textwrap.dedent("""
        [podcast]
        title = "Earful"
        description = "desc"
        author = "Me"
        email = "me@example.com"

        [voices]
        host_a = "am_michael"
        host_b = "af_heart"

        [tts]
        model = "mlx-community/Kokoro-82M-bf16"
        pause_ms = 400
        sample_rate = 24000
    """))
    for k in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_URL_BASE"):
        monkeypatch.setenv(k, f"val-{k}")
    monkeypatch.setenv("R2_PUBLIC_URL_BASE", "https://pub-x.r2.dev/")

    c = cfg.load_config(toml_path=str(toml), env_path="/nonexistent")

    assert c.podcast.title == "Earful"
    assert c.podcast.explicit is False
    assert c.voices["host_a"] == "am_michael"
    assert c.pause_ms == 400
    assert c.r2.bucket == "val-R2_BUCKET"
    assert c.r2.public_base == "https://pub-x.r2.dev"  # trailing slash stripped


def test_load_config_missing_env_raises(tmp_path, monkeypatch):
    toml = tmp_path / "config.toml"
    toml.write_text('[podcast]\ntitle="t"\ndescription="d"\nauthor="a"\nemail="e"\n[voices]\nhost_a="am_michael"\nhost_b="af_heart"\n')
    for k in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_URL_BASE"):
        monkeypatch.delenv(k, raising=False)
    import pytest
    with pytest.raises(RuntimeError):
        cfg.load_config(toml_path=str(toml), env_path="/nonexistent")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'config'` or AttributeError).

- [ ] **Step 3: Write `config.py`**

```python
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Podcast:
    title: str
    description: str
    author: str
    email: str
    language: str
    explicit: bool
    category: str
    link: str


@dataclass(frozen=True)
class R2Creds:
    endpoint: str
    access_key_id: str
    secret_access_key: str
    bucket: str
    public_base: str


@dataclass(frozen=True)
class Config:
    podcast: Podcast
    voices: dict[str, str]
    tts_model: str
    lang_code: str
    pause_ms: int
    sample_rate: int
    r2: R2Creds


def load_config(toml_path: str = "config.toml", env_path: str = ".env") -> Config:
    load_dotenv(env_path)
    data = tomllib.loads(Path(toml_path).read_text())
    p = data["podcast"]
    podcast = Podcast(
        title=p["title"],
        description=p["description"],
        author=p["author"],
        email=p["email"],
        language=p.get("language", "en-us"),
        explicit=bool(p.get("explicit", False)),
        category=p.get("category", "Education"),
        link=p.get("link", ""),
    )
    tts = data.get("tts", {})

    def env(key: str) -> str:
        v = os.getenv(key)
        if not v:
            raise RuntimeError(f"Missing required env var: {key} (set it in .env)")
        return v

    r2 = R2Creds(
        endpoint=env("R2_ENDPOINT"),
        access_key_id=env("R2_ACCESS_KEY_ID"),
        secret_access_key=env("R2_SECRET_ACCESS_KEY"),
        bucket=env("R2_BUCKET"),
        public_base=env("R2_PUBLIC_URL_BASE").rstrip("/"),
    )
    return Config(
        podcast=podcast,
        voices=dict(data["voices"]),
        tts_model=tts.get("model", "mlx-community/Kokoro-82M-bf16"),
        lang_code=tts.get("lang_code", "a"),
        pause_ms=int(tts.get("pause_ms", 400)),
        sample_rate=int(tts.get("sample_rate", 24000)),
        r2=r2,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: typed config loader for .env + config.toml"
```

---

## Task 3: Episode model (`episode.py`)

**Files:**
- Create: `episode.py`
- Test: `tests/test_episode.py`

- [ ] **Step 1: Write the failing test**

```python
import json
import pytest
import episode as ep


def test_load_episode_parses_turns(tmp_path):
    path = tmp_path / "ep.json"
    path.write_text(json.dumps({
        "title": "Intro to X",
        "description": "A primer.",
        "scratchpad": "ignored planning notes",
        "turns": [
            {"speaker": "host_a", "text": "Hello."},
            {"speaker": "host_b", "text": "Hi there."},
        ],
    }))
    e = ep.load_episode(str(path))
    assert e.title == "Intro to X"
    assert e.description == "A primer."
    assert len(e.turns) == 2
    assert e.turns[0].speaker == "host_a"
    assert e.turns[1].text == "Hi there."


def test_load_episode_empty_turns_raises(tmp_path):
    path = tmp_path / "ep.json"
    path.write_text(json.dumps({"title": "t", "description": "d", "turns": []}))
    with pytest.raises(ValueError):
        ep.load_episode(str(path))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_episode.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'episode'`).

- [ ] **Step 3: Write `episode.py`**

```python
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Turn:
    speaker: str
    text: str


@dataclass(frozen=True)
class Episode:
    title: str
    description: str
    turns: list[Turn]


def load_episode(path: str) -> Episode:
    data = json.loads(Path(path).read_text())
    turns = [Turn(speaker=t["speaker"], text=t["text"]) for t in data["turns"]]
    if not turns:
        raise ValueError("episode has no turns")
    return Episode(title=data["title"], description=data["description"], turns=turns)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_episode.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add episode.py tests/test_episode.py
git commit -m "feat: episode JSON model and loader"
```

---

## Task 4: Feed pure helpers (`feed.py` part 1)

**Files:**
- Create: `feed.py`
- Test: `tests/test_feed_helpers.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime, timezone
import feed


def test_slugify():
    assert feed.slugify("Intro to X: Part 1!") == "intro-to-x-part-1"
    assert feed.slugify("") == "episode"


def test_make_guid_is_stable_and_content_derived():
    g1 = feed.make_guid(b"abc")
    g2 = feed.make_guid(b"abc")
    g3 = feed.make_guid(b"xyz")
    assert g1 == g2
    assert g1 != g3
    assert len(g1) == 64  # sha256 hex


def test_rfc822_format():
    dt = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
    s = feed.rfc822(dt)
    assert "29 May 2026" in s
    assert s.endswith("+0000")


def test_fmt_duration():
    assert feed._fmt_duration(75) == "1:15"
    assert feed._fmt_duration(3725) == "1:02:05"


def test_public_url():
    assert feed.public_url("https://pub-x.r2.dev/", "audio/a.mp3") == "https://pub-x.r2.dev/audio/a.mp3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_feed_helpers.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'feed'`).

- [ ] **Step 3: Write `feed.py` (helpers only for now)**

```python
import hashlib
import re
from datetime import datetime, timezone
from email.utils import format_datetime


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s or "episode"


def make_guid(mp3_bytes: bytes) -> str:
    return hashlib.sha256(mp3_bytes).hexdigest()


def rfc822(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt)


def _fmt_duration(secs: int) -> str:
    h, rem = divmod(int(secs), 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


def public_url(base: str, key: str) -> str:
    return f"{base.rstrip('/')}/{key}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_feed_helpers.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add feed.py tests/test_feed_helpers.py
git commit -m "feat: feed helper functions (slug, guid, rfc822, duration, url)"
```

---

## Task 5: Manifest serialization (`feed.py` part 2)

**Files:**
- Modify: `feed.py` (add `EpisodeRecord` + manifest functions)
- Test: `tests/test_manifest.py`

- [ ] **Step 1: Write the failing test**

```python
import feed


def _rec(title="Ep", guid="g1"):
    return feed.EpisodeRecord(
        title=title, description="d", guid=guid,
        audio_url="https://pub-x.r2.dev/audio/a.mp3",
        length_bytes=123, duration_secs=75, pubdate="Fri, 29 May 2026 12:00:00 +0000",
    )


def test_manifest_round_trip():
    records = [_rec("A", "g1"), _rec("B", "g2")]
    text = feed.manifest_to_json(records)
    back = feed.manifest_from_json(text)
    assert back == records


def test_manifest_from_empty_string_list():
    assert feed.manifest_from_json("[]") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_manifest.py -v`
Expected: FAIL (`AttributeError: module 'feed' has no attribute 'EpisodeRecord'`).

- [ ] **Step 3: Add to `feed.py`** (append after the helpers; keep imports at top — add `import json`, `from dataclasses import dataclass, asdict`)

```python
import json
from dataclasses import dataclass, asdict


@dataclass
class EpisodeRecord:
    title: str
    description: str
    guid: str
    audio_url: str
    length_bytes: int
    duration_secs: int
    pubdate: str


def manifest_to_json(records: list[EpisodeRecord]) -> str:
    return json.dumps([asdict(r) for r in records], indent=2)


def manifest_from_json(text: str) -> list[EpisodeRecord]:
    return [EpisodeRecord(**r) for r in json.loads(text)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_manifest.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add feed.py tests/test_manifest.py
git commit -m "feat: episode manifest record and JSON (de)serialization"
```

---

## Task 6: RSS rendering (`feed.py` part 3)

**Files:**
- Modify: `feed.py` (add `render_feed`)
- Test: `tests/test_render_feed.py`

- [ ] **Step 1: Write the failing test**

```python
import xml.etree.ElementTree as ET
import config as cfg
import feed


def _podcast():
    return cfg.Podcast(
        title="Earful", description="desc", author="Me", email="me@example.com",
        language="en-us", explicit=False, category="Education", link="",
    )


def _rec(title, guid):
    return feed.EpisodeRecord(
        title=title, description="A & B <test>", guid=guid,
        audio_url="https://pub-x.r2.dev/audio/a.mp3",
        length_bytes=999, duration_secs=3725, pubdate="Fri, 29 May 2026 12:00:00 +0000",
    )


def test_render_feed_is_valid_xml_with_essentials():
    xml = feed.render_feed(_podcast(), [_rec("First", "g1")], "https://pub-x.r2.dev")
    root = ET.fromstring(xml)  # raises if malformed; proves escaping works
    assert root.tag == "rss"
    assert "<enclosure" in xml
    assert 'length="999"' in xml
    assert 'type="audio/mpeg"' in xml
    assert "g1" in xml
    assert "1:02:05" in xml  # itunes:duration
    assert "https://pub-x.r2.dev/cover.png" in xml  # channel image


def test_render_feed_newest_first():
    xml = feed.render_feed(_podcast(), [_rec("Old", "g1"), _rec("New", "g2")], "https://pub-x.r2.dev")
    assert xml.index("New") < xml.index("Old")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_render_feed.py -v`
Expected: FAIL (`AttributeError: module 'feed' has no attribute 'render_feed'`).

- [ ] **Step 3: Add `render_feed` to `feed.py`** (add `from xml.sax.saxutils import escape` to imports)

```python
from xml.sax.saxutils import escape


def render_feed(podcast, records: list[EpisodeRecord], public_base: str) -> str:
    cover = public_url(public_base, "cover.png")
    explicit = "yes" if podcast.explicit else "no"
    items = []
    for r in reversed(records):  # manifest stored oldest-first; feed shows newest-first
        items.append(
            "    <item>\n"
            f"      <title>{escape(r.title)}</title>\n"
            f"      <description>{escape(r.description)}</description>\n"
            f'      <enclosure url="{escape(r.audio_url)}" length="{r.length_bytes}" type="audio/mpeg"/>\n'
            f'      <guid isPermaLink="false">{r.guid}</guid>\n'
            f"      <pubDate>{r.pubdate}</pubDate>\n"
            f"      <itunes:duration>{_fmt_duration(r.duration_secs)}</itunes:duration>\n"
            f"      <itunes:explicit>{explicit}</itunes:explicit>\n"
            "    </item>"
        )
    items_xml = "\n".join(items)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">\n'
        "  <channel>\n"
        f"    <title>{escape(podcast.title)}</title>\n"
        f"    <description>{escape(podcast.description)}</description>\n"
        f"    <language>{escape(podcast.language)}</language>\n"
        f"    <link>{escape(podcast.link or public_base)}</link>\n"
        f"    <itunes:author>{escape(podcast.author)}</itunes:author>\n"
        f"    <itunes:owner><itunes:name>{escape(podcast.author)}</itunes:name>"
        f"<itunes:email>{escape(podcast.email)}</itunes:email></itunes:owner>\n"
        f'    <itunes:image href="{escape(cover)}"/>\n'
        f'    <itunes:category text="{escape(podcast.category)}"/>\n'
        f"    <itunes:explicit>{explicit}</itunes:explicit>\n"
        f"{items_xml}\n"
        "  </channel>\n"
        "</rss>\n"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_render_feed.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add feed.py tests/test_render_feed.py
git commit -m "feat: render valid podcast RSS from manifest"
```

---

## Task 7: R2 storage (`storage.py`)

**Files:**
- Create: `storage.py`
- Test: `tests/test_storage_integration.py`

This task hits live R2 (creds already verified). The round-trip test is an integration test; it's fast and reliable.

- [ ] **Step 1: Write the failing test**

```python
import config as cfg
from storage import Storage


def test_r2_round_trip():
    c = cfg.load_config()
    s = Storage(c.r2)
    key = "earful-test/storage-it.json"
    url = s.upload_bytes(b'{"ok": true}', key, "application/json")
    assert url == f"{c.r2.public_base}/{key}"
    assert s.download_bytes(key) == b'{"ok": true}'
    assert s.download_bytes("earful-test/does-not-exist.json") is None
    s.delete(key)
    assert s.download_bytes(key) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_storage_integration.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'storage'`).

- [ ] **Step 3: Write `storage.py`**

```python
import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError


def _public_url(base: str, key: str) -> str:
    return f"{base.rstrip('/')}/{key}"


class Storage:
    def __init__(self, r2) -> None:
        self._s3 = boto3.client(
            "s3",
            endpoint_url=r2.endpoint,
            aws_access_key_id=r2.access_key_id,
            aws_secret_access_key=r2.secret_access_key,
            config=BotoConfig(region_name="auto", signature_version="s3v4"),
        )
        self._bucket = r2.bucket
        self._base = r2.public_base

    def upload_file(self, path: str, key: str, content_type: str) -> str:
        self._s3.upload_file(path, self._bucket, key, ExtraArgs={"ContentType": content_type})
        return _public_url(self._base, key)

    def upload_bytes(self, data: bytes, key: str, content_type: str) -> str:
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)
        return _public_url(self._base, key)

    def download_bytes(self, key: str) -> bytes | None:
        try:
            return self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None
            raise

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=key)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_storage_integration.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add storage.py tests/test_storage_integration.py
git commit -m "feat: R2 storage client (upload/download/delete)"
```

---

## Task 8: Audio assembly pure functions (`tts.py` part 1)

**Files:**
- Create: `tts.py`
- Test: `tests/test_audio_assembly.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
import tts


def test_assemble_inserts_silence_between_turns_only():
    a = np.ones(10, dtype=np.float32)
    b = np.ones(20, dtype=np.float32)
    out = tts.assemble_audio([a, b], pause_samples=5)
    assert len(out) == 10 + 5 + 20  # no leading/trailing silence
    assert np.all(out[10:15] == 0.0)


def test_assemble_single_turn_has_no_silence():
    a = np.ones(10, dtype=np.float32)
    assert len(tts.assemble_audio([a], pause_samples=5)) == 10


def test_to_int16_scales_and_clips():
    x = np.array([0.0, 1.0, -1.0, 2.0, -2.0], dtype=np.float32)
    out = tts.to_int16(x)
    assert out.dtype == np.int16
    assert out[0] == 0
    assert out[1] == 32767
    assert out[2] == -32767
    assert out[3] == 32767  # clipped
    assert out[4] == -32767  # clipped
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_audio_assembly.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'tts'`).

- [ ] **Step 3: Write `tts.py` (pure functions only)**

```python
import numpy as np


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_audio_assembly.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add tts.py tests/test_audio_assembly.py
git commit -m "feat: audio assembly and int16 conversion"
```

---

## Task 9: Kokoro synthesis + MP3 export (`tts.py` part 2)

**Files:**
- Modify: `tts.py` (add `synthesize`, `write_mp3`)
- Test: `tests/test_write_mp3.py`

**API note (do this first):** mlx-audio's `generate()` API has varied across versions. Before writing `synthesize`, confirm the installed API by reading the package:
```bash
.venv/bin/python -c "import mlx_audio.tts.utils as u; help(u.load_model)"
```
and skim `from mlx_audio.tts.generate import generate_audio` / the model's `.generate` signature. The code below matches the common `load_model(...).generate(text=..., voice=..., lang_code=...)` yielding objects with `.audio`. Adjust attribute access if the installed version differs; keep the function shape identical so the rest of the pipeline is unaffected.

- [ ] **Step 1: Write the failing test** (covers MP3 export only — no model needed)

```python
import os
import numpy as np
import tts


def test_write_mp3_produces_playable_file(tmp_path):
    sr = 24000
    t = np.linspace(0, 1.0, sr, dtype=np.float32)
    tone = (0.2 * np.sin(2 * np.pi * 440 * t))
    samples = tts.to_int16(tone)
    out = tmp_path / "tone.mp3"
    duration, size = tts.write_mp3(samples, sr, str(out), {"title": "Tone", "artist": "Earful"})
    assert out.exists()
    assert size > 0
    assert duration == 1  # ~1 second, rounded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_write_mp3.py -v`
Expected: FAIL (`AttributeError: module 'tts' has no attribute 'write_mp3'`).

- [ ] **Step 3: Add `synthesize` and `write_mp3` to `tts.py`** (add imports `import os, subprocess, tempfile` and `import soundfile as sf`)

```python
import os
import subprocess
import tempfile

import soundfile as sf


def synthesize(episode, config) -> np.ndarray:
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
        subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-b:a", "128k", *meta, mp3_path],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    finally:
        os.unlink(wav_path)
    duration = int(round(len(samples_int16) / sample_rate))
    return duration, os.path.getsize(mp3_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_write_mp3.py -v`
Expected: PASS (1 test). Requires ffmpeg on PATH (Task 1).

- [ ] **Step 5: Integration smoke test for real Kokoro synthesis**

Run:
```bash
.venv/bin/python - <<'PY'
import numpy as np, soundfile as sf
from config import load_config
from episode import Episode, Turn
import tts
c = load_config()
ep = Episode("Smoke", "d", [Turn("host_a", "Hello, this is the first host."),
                            Turn("host_b", "And I am the second host. Nice to meet you.")])
samples = tts.synthesize(ep, c)
tts.write_mp3(samples, c.sample_rate, "out_smoke.mp3", {"title": "Smoke"})
print("samples:", len(samples), "-> out_smoke.mp3")
PY
```
Expected: first run downloads the Kokoro model (slow, one-time), then writes `out_smoke.mp3`. Play it: `afplay out_smoke.mp3` — you should hear two distinct voices with a pause between turns. If the API differs, adjust per the API note above. Delete `out_smoke.mp3` after: `rm out_smoke.mp3`.

- [ ] **Step 6: Commit**

```bash
git add tts.py tests/test_write_mp3.py
git commit -m "feat: Kokoro synthesis and MP3 export"
```

---

## Task 10: Cover art (`tools/make_cover.py`)

**Files:**
- Create: `tools/make_cover.py`

Podcast feeds require square channel artwork (1400–3000px). This generates a simple, clean placeholder and uploads it to R2 as `cover.png` (the key `feed.render_feed` references).

- [ ] **Step 1: Write `tools/make_cover.py`**

```python
"""Generate a simple square cover and upload it to R2 as cover.png. Run once.

Usage: .venv/bin/python tools/make_cover.py
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import load_config  # noqa: E402
from storage import Storage  # noqa: E402

SIZE = 1500


def make_cover(title: str, out_path: str) -> None:
    img = Image.new("RGB", (SIZE, SIZE), (22, 28, 38))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", 220)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), title, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((SIZE - w) / 2, (SIZE - h) / 2 - bbox[1]), title, fill=(245, 240, 230), font=font)
    img.save(out_path, "PNG")


if __name__ == "__main__":
    c = load_config()
    out = "out/cover.png"
    Path("out").mkdir(exist_ok=True)
    make_cover(c.podcast.title, out)
    url = Storage(c.r2).upload_file(out, "cover.png", "image/png")
    print("uploaded cover:", url)
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python tools/make_cover.py`
Expected: prints `uploaded cover: https://pub-….r2.dev/cover.png`. Open that URL in a browser — you should see the cover.

- [ ] **Step 3: Commit**

```bash
git add tools/make_cover.py
git commit -m "feat: cover art generator + upload"
```

---

## Task 11: Orchestrator (`produce.py`)

**Files:**
- Create: `produce.py`
- Test: `tests/test_produce_dryrun.py`

- [ ] **Step 1: Write the failing test** (dry-run, with synthesis monkeypatched so no model loads)

```python
import json
import xml.etree.ElementTree as ET
import numpy as np
import produce
import tts


def test_produce_dry_run_writes_local_feed(tmp_path, monkeypatch):
    # Fake synthesis: 0.3s of silence, so no model download and ffmpeg still runs.
    monkeypatch.setattr(tts, "synthesize", lambda episode, config: np.zeros(int(24000 * 0.3), dtype=np.int16))
    monkeypatch.chdir(tmp_path)
    # Minimal config.toml + env in the temp cwd.
    (tmp_path / "config.toml").write_text(
        '[podcast]\ntitle="Earful"\ndescription="d"\nauthor="Me"\nemail="me@x.com"\n'
        '[voices]\nhost_a="am_michael"\nhost_b="af_heart"\n'
        '[tts]\nsample_rate=24000\npause_ms=400\n'
    )
    for k in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        monkeypatch.setenv(k, "x")
    monkeypatch.setenv("R2_PUBLIC_URL_BASE", "https://pub-x.r2.dev")
    ep = tmp_path / "ep.json"
    ep.write_text(json.dumps({
        "title": "Test Episode", "description": "d",
        "turns": [{"speaker": "host_a", "text": "Hi."}, {"speaker": "host_b", "text": "Hello."}],
    }))

    result = produce.produce(str(ep), dry_run=True)

    assert (tmp_path / "out" / "feed.xml").exists()
    assert (tmp_path / "out" / "test-episode.mp3").exists()
    xml = (tmp_path / "out" / "feed.xml").read_text()
    ET.fromstring(xml)
    assert "Test Episode" in xml
    assert "https://pub-x.r2.dev/audio/test-episode-" in xml  # deterministic audio URL
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_produce_dryrun.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'produce'`).

- [ ] **Step 3: Write `produce.py`**

```python
import argparse
from datetime import datetime, timezone
from pathlib import Path

import config as config_mod
import feed
import tts
from episode import load_episode
from storage import Storage

MANIFEST_KEY = "episodes.json"
FEED_KEY = "feed.xml"


def produce(episode_path: str, dry_run: bool) -> str:
    cfg = config_mod.load_config()
    episode = load_episode(episode_path)
    samples = tts.synthesize(episode, cfg)

    Path("out").mkdir(exist_ok=True)
    slug = feed.slugify(episode.title)
    mp3_path = f"out/{slug}.mp3"
    tags = {"title": episode.title, "artist": cfg.podcast.title, "album": cfg.podcast.title}
    duration, size = tts.write_mp3(samples, cfg.sample_rate, mp3_path, tags)

    guid = feed.make_guid(Path(mp3_path).read_bytes())
    audio_key = f"audio/{slug}-{guid[:8]}.mp3"
    audio_url = feed.public_url(cfg.r2.public_base, audio_key)
    pubdate = feed.rfc822(datetime.now(timezone.utc))
    record = feed.EpisodeRecord(
        title=episode.title, description=episode.description, guid=guid,
        audio_url=audio_url, length_bytes=size, duration_secs=duration, pubdate=pubdate,
    )

    if dry_run:
        local = Path("out/episodes.json")
        manifest = feed.manifest_from_json(local.read_text()) if local.exists() else []
        manifest.append(record)
        local.write_text(feed.manifest_to_json(manifest))
        Path("out/feed.xml").write_text(feed.render_feed(cfg.podcast, manifest, cfg.r2.public_base))
        print(f"[dry-run] wrote {mp3_path}, out/feed.xml, out/episodes.json")
        return "out/feed.xml"

    storage = Storage(cfg.r2)
    storage.upload_file(mp3_path, audio_key, "audio/mpeg")
    raw = storage.download_bytes(MANIFEST_KEY)
    manifest = feed.manifest_from_json(raw.decode()) if raw else []
    manifest.append(record)
    storage.upload_bytes(feed.manifest_to_json(manifest).encode(), MANIFEST_KEY, "application/json")
    feed_url = storage.upload_bytes(
        feed.render_feed(cfg.podcast, manifest, cfg.r2.public_base).encode(),
        FEED_KEY, "application/rss+xml; charset=utf-8",
    )
    print(f"Published: {episode.title}\nFeed: {feed_url}")
    return feed_url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Produce and publish an Earful episode.")
    parser.add_argument("episode_json", help="path to the episode JSON")
    parser.add_argument("--dry-run", action="store_true", help="render locally; skip R2 upload")
    args = parser.parse_args()
    produce(args.episode_json, args.dry_run)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_produce_dryrun.py -v`
Expected: PASS (1 test). Requires ffmpeg.

- [ ] **Step 5: Full suite green**

Run: `.venv/bin/pytest -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add produce.py tests/test_produce_dryrun.py
git commit -m "feat: produce.py orchestrator with dry-run"
```

---

## Task 12: Procedure doc (`CLAUDE.md`)

**Files:**
- Create: `CLAUDE.md`

This is the "trigger": it tells Claude exactly what to do when you give a topic.

- [ ] **Step 1: Write `CLAUDE.md`**

````markdown
# Earful — how to make an episode

When the user gives a topic ("make an episode about X"), do all of this without
stopping for review (one-shot):

## 1. Freshness probe, then research
- Do ONE quick web search to gauge whether my knowledge of the topic is current
  and sufficient.
- If it's solid, write from my own knowledge. If it's stale, thin, or fast-moving,
  do fuller research (search + fetch a few good sources) before writing.

## 2. Write the script to `episode.json`
Two-host conversation between `host_a` and `host_b` (symmetric — no host/guest).
Schema:
```json
{
  "title": "Concise episode title",
  "description": "1-3 sentence summary shown in the podcast app",
  "scratchpad": "My outline/plan before writing turns (ignored by the pipeline)",
  "turns": [
    {"speaker": "host_a", "text": "..."},
    {"speaker": "host_b", "text": "..."}
  ]
}
```
Rules:
- Each turn is short: ~1-2 sentences, roughly <=250 characters. This keeps each
  turn under Kokoro's ~510-token synthesis limit and sounds natural.
- Plan in `scratchpad` first, then write turns.
- Conversational, with natural give-and-take; the two hosts build on each other.
- Target ~12-18 minutes (~2000-2800 words total across both hosts).
- Open with a brief hook, close with a short recap.
- No stage directions, sound-effect cues, or markdown inside `text` — plain spoken
  sentences only (it all gets read aloud verbatim).

## 3. Produce and publish
```bash
.venv/bin/python produce.py episode.json
```
This synthesizes audio, uploads to R2, regenerates the feed, and prints the feed URL.
Use `--dry-run` to render locally (out/) without uploading when testing.

## Notes
- Config (podcast metadata, voices) lives in `config.toml`; R2 creds in `.env`.
- `verify_r2.py` re-checks R2 connectivity if publishing fails.
- The feed lives at `<R2_PUBLIC_URL_BASE>/feed.xml`; the user subscribes their
  podcast app to it once.
````

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: episode-production procedure for Claude"
```

---

## Task 13: First real episode + subscribe (manual validation)

**Files:** none (validation only)

- [ ] **Step 1: Ensure the cover exists** (Task 10 ran). If not: `.venv/bin/python tools/make_cover.py`

- [ ] **Step 2: Write a tiny real `episode.json`** (3-4 short turns) by hand or via Claude, then dry-run:

Run: `.venv/bin/python produce.py episode.json --dry-run`
Expected: `out/episode-*.mp3` plays correctly (`afplay out/<slug>.mp3`); `out/feed.xml` is valid.

- [ ] **Step 3: Publish for real**

Run: `.venv/bin/python produce.py episode.json`
Expected: prints `Feed: https://pub-….r2.dev/feed.xml`.

- [ ] **Step 4: Validate the live feed**

Run:
```bash
curl -s -A "Mozilla/5.0" "$(grep '^R2_PUBLIC_URL_BASE=' .env | cut -d= -f2- | tr -d '\r')/feed.xml" | head -40
```
Expected: valid RSS with your episode's `<item>` and a reachable `<enclosure url=...>`. Optionally paste the feed URL into https://podba.se/validate/ or https://www.castfeedvalidator.com/.

- [ ] **Step 5: Subscribe**

In your podcast app, add the feed by URL (`…/feed.xml`). In Pocket Casts:
Profile → Add Podcast → (URL) → paste. Confirm the episode appears and plays.

- [ ] **Step 6: Commit any config tweaks made during validation**

```bash
git add -A && git commit -m "chore: first-episode validation tweaks"
```

---

## Self-Review Notes

- **Spec coverage:** format (two-host) → Task 12 schema; mlx-audio/Kokoro → Task 9; R2 hosting → Task 7; freshness-probe→research → Task 12; one-shot workflow → Task 11/12; feed correctness (GUID/length/duration) → Tasks 5/6; manifest as source of truth in R2 → Task 11; cover art → Task 10; in-house feed code → Task 6; trigger via prompt (no skill) → Task 12; testing (sample synth, feed validation, dry-run) → Tasks 9/11/13. All covered.
- **Known API risk:** mlx-audio `generate()` signature varies by version — Task 9 includes an explicit "read the installed API first" step. This is the only place the exact code may need adjustment; the function shape is fixed so nothing downstream changes.
- **Python 3.14 note:** pydub is intentionally NOT used (it depends on the removed `audioop` module); MP3 export goes through ffmpeg directly.
