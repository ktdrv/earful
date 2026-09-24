# Earful

Tell Claude Code a topic. Get a two-host podcast episode in your podcast app a few minutes later. No studio, no editing.

**topic → one command → it's on your phone.** Earful voices a two-person script with a TTS engine, masters it to MP3, uploads it to object storage, and regenerates a standard RSS feed your podcast app is subscribed to.

```
script.md ─▶ produce.py
                 ├─ voice the dialogue (Kokoro locally, or Gemini TTS)
                 ├─ master → MP3 (ffmpeg, ID3 tags)
                 ├─ upload MP3 to object storage (Cloudflare R2 by default)
                 └─ rebuild episodes.json manifest + feed.xml, upload feed
                              │
   your podcast app, subscribed to <PUBLIC_URL>/feed.xml, polls ─▶ new episode appears
```

- **TTS**, two engines, picked with `[tts] engine` in `config.toml` or `produce.py --engine`:
  - **Kokoro** ([Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) via [mlx-audio](https://github.com/Blaizzy/mlx-audio), `tts.py`): free and local, but Apple Silicon only. Renders each turn separately and adds its own pauses, overlap and mic realism.
  - **Gemini** ([Gemini TTS](https://ai.google.dev/gemini-api/docs/speech-generation), `gemini_tts.py`): a paid API, about $0.25 per 15 minutes, that runs anywhere. It voices both hosts together in its native dialogue mode and sounds much more natural.
- **Hosting**: any S3-compatible store (R2, AWS S3, Backblaze B2, Spaces, Wasabi, MinIO). R2 is the default because its free tier serves a public URL with no custom domain and no egress fees. See [Hosting](#hosting).
- **Feed**: plain RSS 2.0 + iTunes tags. Works in every podcast app.

## Setup (~5 minutes, mostly the bucket)

You need [uv](https://docs.astral.sh/uv/) and ffmpeg (`brew install ffmpeg`, or your package manager's).

```bash
uv sync                                 # installs everything; Kokoro's deps only on Apple Silicon
cp config.toml.example config.toml      # podcast name, the two hosts + voices, the TTS engine
cp .env.example .env                    # storage credentials, and GEMINI_API_KEY for Gemini
```

The example config uses Kokoro. **Not on Apple Silicon?** Set `engine = "gemini"` under `[tts]` in `config.toml`. For Kokoro, also `brew install espeak-ng` (its fallback for words it doesn't know), and optionally `cp pronunciations.toml.example pronunciations.toml` to start a pronunciation dictionary. On a Mac that will only use Gemini, `uv sync --no-group kokoro` skips Kokoro's large dependencies (PyTorch among them).

**The bucket.** On Cloudflare R2: create a bucket, enable its **public dev URL**, and make an **Object Read & Write** API token scoped to it. Drop the five values into `.env` (it's annotated). Any other S3-compatible store works too; see [Hosting](#hosting).

**Gemini** needs a key from [Google AI Studio](https://aistudio.google.com/apikey) in `.env` as `GEMINI_API_KEY`, on a project with billing enabled (free-tier requests may be used to train Google's models).

```bash
uv run verify_r2.py                     # put→get→public-fetch→delete; never prints secrets
uv run tools/make_cover.py --upload     # render + upload cover.png and daily/cover.png (once)
```

The covers are Earful's own wordmark; swap in your own art for your show. Then subscribe your podcast app to `<R2_PUBLIC_URL_BASE>/feed.xml`, once. Every future episode shows up on its own.

## Making an episode

**With Claude Code (the intended way).** Open this repo in Claude Code and say *"make an episode about X."* It asks a couple of calibration questions, researches if its knowledge is thin, writes the two-host script as a Markdown file, and runs the pipeline. [`CLAUDE.md`](CLAUDE.md) is the full playbook it follows: host personas, conversational pacing, pause and overlap direction, pronunciation. Edit it to taste; it's written for a smart, informed listener who wants depth.

**By hand.** Episodes are plain-Markdown **audio-scripts**: frontmatter plus a dialogue between the two hosts. They live in `scripts_dir` (a config value; point it at any folder you like, such as a notes vault). See `example.md`:

```markdown
---
title: Episode title
description: Shown in the podcast app
---

THEO: Wait — you're telling me the model was the easy part? (beat) That's the whole story.
MARA: That's exactly what I'm telling you. The hard part was getting anyone to trust it —
THEO: —and that took months, not the two weeks everyone budgeted.
```

```bash
uv run produce.py my-episode                  # resolves scripts_dir/my-episode.md
uv run produce.py my-episode --dry-run        # render to out/ only, no upload
uv run produce.py my-episode --engine gemini  # override the configured engine for one run
uv run produce.py my-episode --feed daily     # publish to a second feed ([feeds.daily] in config.toml)
```

Each line starts with a host **cue**, the host's `name` from `config.toml` and a colon; a turn runs to the next cue. Direction goes in parentheticals and isn't read aloud: `(beat)` / `(pause)` / `(long pause)` / `(pause: 500)` for a pause, `…` for a trail-off, a trailing `—` to have the next host talk over you, `(breath)`, and `(faster)`/`(slower)` to lead a line. `[word](/ˈɪpə/)` hand-sets a pronunciation for Kokoro. Gemini also performs vocal cues like `(laughs)` and takes a line-opening parenthetical like `(dryly)` as delivery direction; Kokoro ignores both. The point is two distinct people reacting to each other, not one explanation split across two voices. `CLAUDE.md` has the why and the craft.

## Configuration

- **`config.toml`**: podcast metadata, the TTS engine, and the two hosts. Each host has a `name`, a Kokoro `voice` (`am_`/`af_` = US male/female, `bm_`/`bf_` = UK; full [voice list](https://github.com/hexgrad/kokoro)), a `gemini_voice` (one of Gemini's [prebuilt voices](https://ai.google.dev/gemini-api/docs/speech-generation#voices)), a stereo `pan` (Kokoro only), and a `persona` that steers how Claude writes that character. The `[tts]` block tunes Kokoro's pacing, per-turn variation and mic realism, and the mastering loudness both engines share. Each field is commented.
- **`pronunciations.toml`** (personal and gitignored; start from `pronunciations.toml.example`): a `term → IPA` dictionary Kokoro applies to every script, so recurring jargon and names come out right without per-script annotation. Add only terms Kokoro actually says wrong, and verify with `uv run tools/check_pron.py`. Gemini works pronunciation out from context and doesn't use it.

## Optional: a daily news brief

`tools/ai-daily.sh` runs Claude Code headless to research and write a ~5-minute AI news brief (the playbook for it is `.claude/commands/ai-daily.md`), then publishes it to a second feed defined by `[feeds.daily]`. It's macOS-flavored (logs to `~/Library/Logs`, notifies on failure) and meant to be fired each morning by a launchd agent or cron. Change the prompt's scope to brief yourself on anything else.

## Hosting

`storage.py` is plain S3 (`boto3`). To use a provider other than R2, point `.env` at it: `R2_ENDPOINT`, the keys, `R2_BUCKET`, the public `R2_PUBLIC_URL_BASE`, and `R2_REGION` (`auto` for R2; the bucket's real region for AWS S3). The bucket must serve its objects publicly so podcast apps can fetch them.

**No object storage at all?** `produce.py --dry-run` writes the finished `feed.xml` and MP3s to `out/`. Host that folder on any static host (GitHub Pages, Netlify, your own server), and set `R2_PUBLIC_URL_BASE` to where you'll serve it so the feed's links resolve; the other `R2_*` vars can stay as placeholders in dry-run.

## Contributing

Issues and pull requests are welcome. The code is small and flat: `produce.py` drives the pipeline, `episode.py` parses scripts, `tts.py` and `gemini_tts.py` are the two engines, and `feed.py` and `storage.py` publish.

```bash
uv run pytest -q
```

The tests need ffmpeg but no API keys and no Apple Silicon: nothing calls a real TTS engine, and `test_storage_integration.py`, the one test that hits live storage, skips unless your `.env` and `config.toml` are set up. CI runs the same suite on Linux for every pull request. A new TTS engine is one module with a `synthesize(episode, config)` function, plus a branch in `produce.py`.

## License

MIT; see [LICENSE](LICENSE).
