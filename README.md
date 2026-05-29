# Earful

Turn any topic into a two-host podcast episode you can listen to in your podcast
app. You write a short script (or have an LLM write it), and Earful synthesizes it
to audio with a local TTS model, uploads it to object storage, and regenerates a
standard podcast RSS feed your app subscribes to once.

The whole loop: **pick a topic → run one command → the episode shows up on your phone.**

## How it works

```
episode.json  ->  produce.py
                    |- synthesize each turn with Kokoro (mlx-audio), two voices
                    |- stitch turns + pauses -> MP3 (ffmpeg) with ID3 tags
                    |- upload MP3 to Cloudflare R2
                    |- append to episodes.json manifest, regenerate feed.xml
                    \- upload feed.xml to R2
                  |
   Your podcast app (subscribed to the R2 feed URL) polls -> new episode appears
```

- **TTS:** [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) via
  [mlx-audio](https://github.com/Blaizzy/mlx-audio) — free, local, fast on Apple
  Silicon. Swappable: TTS is isolated behind `tts.synthesize(episode, config)`.
- **Hosting:** Cloudflare R2 (S3-compatible). Any S3-compatible store works with
  minor changes to `storage.py`.
- **Feed:** standard RSS 2.0 + iTunes tags — works in any podcast app, not just one.

## Setup (macOS / Apple Silicon)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
brew install ffmpeg espeak-ng           # both fail silently if missing

cp config.toml.example config.toml      # edit podcast name, voices, etc.
cp .env.example .env                     # fill in your R2 credentials
```

R2 setup: create a bucket, enable its public development URL, and create an
"Object Read & Write" API token scoped to the bucket. Put the resulting values in
`.env`. Run `python verify_r2.py` to confirm connectivity, then upload a cover
image once with `python tools/make_cover.py`.

## Usage

Write an `episode.json`:

```json
{
  "title": "Episode title",
  "description": "Shown in the podcast app",
  "turns": [
    {"speaker": "host_a", "text": "Wait, so you're telling me the model was the easy part?"},
    {"speaker": "host_b", "text": "That's exactly what I'm telling you. The hard part was getting anyone to trust it -- and that took months, not the two weeks everyone budgeted for."}
  ]
}
```

Then produce and publish:

```bash
python produce.py episode.json            # synthesize, upload, regenerate feed
python produce.py episode.json --dry-run  # render to out/ locally, skip upload
```

Subscribe your podcast app to `<R2_PUBLIC_URL_BASE>/feed.xml` once. Every future
episode appears automatically.

Write it as a real conversation between two distinct people, not one explanation
split across two voices — vary turn length freely (one-word reactions through
multi-sentence points). Kokoro auto-chunks long turns at sentence boundaries, so
there's no hard length limit per turn; only its ~510-phoneme-token *synthesis* cap
matters, and that only bites a single turn longer than a few sentences.
`CLAUDE.md` documents the full LLM-driven authoring procedure (personas, pacing,
pronunciation overrides) if you drive this with Claude Code.

## Tests

```bash
.venv/bin/pytest -q
```

One test (`test_storage_integration.py`) hits live R2 using your `.env`.

## License

MIT — see [LICENSE](LICENSE).
