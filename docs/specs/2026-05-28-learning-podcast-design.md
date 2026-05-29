# Earful — AI Learning Podcast Pipeline — Design

**Date:** 2026-05-28
**Goal:** Go from "tell me about this topic" to listening in any podcast app, with nothing in between. (Pocket Casts is the author's client, but the design targets the standard podcast RSS format, not any one app.)

## Summary

Prompt Claude (in this directory) with a topic. Claude researches it, writes a
two-host conversational script, and immediately runs a local pipeline that voices
the script with a free/local TTS model, uploads the audio to public cloud storage,
and regenerates the podcast RSS feed. Your podcast app — subscribed once to the feed
URL — polls and the new episode appears. Fully hands-off after the prompt.

## Decisions (locked)

| Decision | Choice | Why |
|---|---|---|
| Format | Two-host conversation | Most engaging for passive learning. |
| Compute | This Mac (Apple Silicon) | Already available; Kokoro runs fast locally. |
| TTS | Kokoro-82M | Free, local, fast on Apple Silicon, multiple distinct high-quality voices. |
| Hosting | Cloudflare R2 (public bucket) | Always-on public URL (`*.r2.dev`), no domain needed, generous free tier. |
| Knowledge | Freshness probe → research if needed | Quick search to gauge if Claude's knowledge is current; do fuller research only when it's stale/thin. Accuracy matters for learning. |
| Workflow | One-shot, hands-off | Topic in → published episode out, no review stop. |
| Trigger | Prompt Claude in this directory (no skill/slash command) | Lowest friction; nothing to install. A project `CLAUDE.md` documents the steps. |
| Feed | Single feed to start | Splitting by subject is a later tweak. |

A fully automated, cron-driven, LLM-API variant (daily episode, zero human) is a
possible future evolution. It costs API money and drops the "prompt you"
interaction, so it's explicitly out of scope for v1.

## Flow

```
You: "make an episode about <topic>"   (prompt Claude in this directory)
  │
  1. Freshness probe + research          ← Claude, web search/fetch
  2. Write two-host script → episode JSON ← Claude
  3. python produce.py episode.json       ← Claude invokes it, no review stop
        ├─ TTS each turn via Kokoro (2 voices)
        ├─ stitch turns + pauses → MP3 + ID3 tags
        ├─ upload MP3 to Cloudflare R2
        ├─ append to episodes manifest, regenerate feed.xml
        └─ upload feed.xml to R2
  │
  Podcast app (subscribed once to the R2 feed URL) polls → episode appears
```

## Components

Kept deliberately small; each has one clear purpose.

1. **`CLAUDE.md` (project)** — documents the procedure Claude follows when prompted:
   probe → research → write episode JSON → run `produce.py`. The "trigger."
2. **Episode JSON** — the interface between Claude and the pipeline:
   ```json
   {
     "title": "string",
     "description": "string (shown in podcast app)",
     "scratchpad": "string — Claude's plan/outline before the turns (improves coherence; ignored by the pipeline)",
     "turns": [
       {"speaker": "host_a", "text": "..."},
       {"speaker": "host_b", "text": "..."}
     ]
   }
   ```
   Speakers are exactly `host_a` / `host_b` (symmetric two-host, no host/guest
   asymmetry), each mapped to a voice in config. **Each turn's `text` stays short —
   ~1–2 sentences / roughly ≤250 chars** — which keeps every turn under Kokoro's
   ~510-token synthesis ceiling and produces natural turn-taking. The `scratchpad`
   field (borrowed from open-notebooklm) lets Claude outline first; the pipeline
   reads only `turns` + metadata.
3. **`produce.py`** — the single command: TTS → stitch → upload → feed → upload.
   Thin orchestrator over the modules below. Supports `--dry-run` (skip upload;
   write MP3 + feed locally for inspection).
4. **`tts.py`** — Kokoro synthesis via **mlx-audio** (`Kokoro-82M-bf16`): synthesize
   **per turn** with that speaker's voice, keep everything as 24 kHz float32 numpy
   arrays (no per-turn WAV files), concatenate with ~0.4s silence between turns,
   scale float32→int16, then export a single MP3 via ffmpeg with ID3 tags. Any
   over-long turn is sentence-split before synthesis and its chunks concatenated.
5. **`feed.py`** — maintains `episodes.json` (durable source of truth) and
   regenerates a valid podcast RSS feed (RSS 2.0 + iTunes namespace). **Correctness
   essentials** (the things that make podcast apps misbehave if wrong): stable,
   content-hash-derived `<guid isPermaLink="false">` per episode (never regenerated);
   `<enclosure>` with the real MP3 byte `length` and `type="audio/mpeg"`; real
   `<itunes:duration>` in seconds; RFC-822 `<pubDate>`; channel `<itunes:image>`,
   `<itunes:category>`, `<itunes:explicit>`, `<itunes:author>`. Reference:
   `vpetersson/podcast-rss-generator` (same S3/R2-hosted-episodes model).
6. **`storage.py`** — Cloudflare R2 upload via boto3 (S3-compatible). Returns
   public URLs for enclosures and feed.
7. **`config.toml` + `.env`** — podcast metadata (name, author, description, cover
   image URL), the two voice IDs, R2 credentials/bucket/public-URL base.

## Data & correctness

- **`episodes.json` is the source of truth.** The feed is regenerated cumulatively
  from it every run, so episodes never disappear across Mac restarts and the feed
  is always valid.
- Each episode gets a stable GUID and an enclosure pointing at its R2 MP3 URL.

## Tech notes

- **TTS: mlx-audio (Metal-native) running `Kokoro-82M-bf16`** — preferred over the
  canonical PyTorch Kokoro, which runs through MPS with flaky fallbacks on Apple
  Silicon. `model.generate(text, voice=...)` yields 24 kHz audio chunks.
  Default voices: one male + one female (e.g. `am_*` / `af_*`), swappable in config.
  Consider Kokoro's voice-blending trick to make the two hosts distinct but related.
- **Two deps that fail silently if missing:** `brew install ffmpeg` (MP3 export) and
  `brew install espeak-ng` (grapheme→phoneme for English G2P).
- **float32→int16 scaling** before MP3 export is mandatory: `(x*32767).astype(np.int16)`.
  Skipping it yields silence or noise.
- **MP3** is the enclosure format (universally supported by podcast apps).
- **Cover art:** podcast apps require square channel artwork (1400–3000px).
  You provide one image, or Claude generates a simple placeholder to start.

## Prior art / references

- **open-notebooklm** (gabrielchua, ~2.6k★) — structured dialogue schema + scratchpad
  + short-line prompt patterns. The main reference for the script-gen step.
- **mlx-audio** (Blaizzy, ~7.1k★) — Metal-native Kokoro on Apple Silicon. The TTS path.
- **Kokoro-FastAPI** (remsky, ~4.9k★) — sentence-boundary chunking + voice blending.
- **podcast-rss-generator** (vpetersson) — feed generation for S3/R2-hosted episodes;
  GUID-from-checksum pattern. The feed reference.
- **podcastfy** (~6.3k★) — mature but over-abstracted and cloud-TTS-centric; what NOT
  to copy for a personal single-purpose tool.

## One-time setup

1. Create R2 bucket + API token; enable public access; note the public URL base.
2. `pip install mlx-audio soundfile boto3 mutagen` (+ feed deps);
   `brew install ffmpeg espeak-ng`.
3. Add a square cover image and upload it once.
4. Generate the first feed and **subscribe your podcast app to the R2 feed URL once.**

## Testing

- `tts.py`: synth a 2-turn sample; verify MP3 plays and contains both voices.
- `feed.py`: validate generated XML against a podcast feed validator and a real
  import in a podcast app.
- `produce.py --dry-run`: full pipeline minus upload; inspect MP3 + feed locally
  before going live.

## Defaults (override anytime)

- Episode length target ~12–18 min (~2000–2800 words across both hosts).
- Single podcast feed, titled **Earful**.
- R2 bucket name: `earful`.
