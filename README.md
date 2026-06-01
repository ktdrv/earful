# Earful

Tell Claude Code a topic. Get a two-host podcast episode in your podcast app a few
minutes later. No studio, no editing, no cloud TTS bill.

**topic → one command → it's on your phone.** Earful voices a short two-person
script with a local TTS model, masters it to MP3, uploads it to object storage, and
regenerates a standard RSS feed your podcast app is subscribed to.

```
episode.json ─▶ produce.py
                 ├─ synthesize each turn with Kokoro (two voices, mlx-audio)
                 ├─ stitch turns + pauses, master → MP3 (ffmpeg, ID3 tags)
                 ├─ upload MP3 to object storage (Cloudflare R2 by default)
                 └─ rebuild episodes.json manifest + feed.xml, upload feed
                              │
   your podcast app, subscribed to <PUBLIC_URL>/feed.xml, polls ─▶ new episode appears
```

- **TTS** — [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) via
  [mlx-audio](https://github.com/Blaizzy/mlx-audio): free, local, fast on Apple
  Silicon. Isolated behind `tts.synthesize(episode, config)`, so swapping engines is
  a one-file change.
- **Hosting** — any S3-compatible store (R2, AWS S3, Backblaze B2, Spaces, Wasabi,
  MinIO). R2 is the default because its free tier serves a public URL with no custom
  domain and no egress fees. See [Hosting](#hosting).
- **Feed** — plain RSS 2.0 + iTunes tags. Works in every podcast app.

> **Requires Apple Silicon.** Kokoro runs on Apple's MLX. ffmpeg does the mastering.

## Setup (~5 minutes, mostly the bucket)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
brew install ffmpeg espeak-ng          # ffmpeg masters; espeak-ng is the G2P fallback

cp config.toml.example config.toml     # podcast name, the two hosts + voices
cp .env.example .env                    # storage credentials (see below)
```

**The bucket.** On Cloudflare R2: create a bucket, enable its **public dev URL**,
and make an **Object Read & Write** API token scoped to it. Drop the five values
into `.env` (it's annotated). Any other S3-compatible store works too — see
[Hosting](#hosting).

```bash
.venv/bin/python verify_r2.py          # put→get→public-fetch→delete; never prints secrets
.venv/bin/python tools/make_cover.py   # generate + upload cover.png (once)
```

Then subscribe your podcast app to `<R2_PUBLIC_URL_BASE>/feed.xml` — once. Every
future episode shows up on its own.

## Making an episode

**With Claude Code (the intended way).** Open this repo in Claude Code and say
*"make an episode about X."* It asks a couple of calibration questions, researches
if its knowledge is thin, writes the two-host script to `episode.json`, and runs the
pipeline. [`CLAUDE.md`](CLAUDE.md) is the full playbook it follows — host personas,
conversational pacing, pause/overlap direction, pronunciation overrides.

**By hand.** Write an `episode.json` and run it yourself:

```json
{
  "title": "Episode title",
  "description": "Shown in the podcast app",
  "turns": [
    {"speaker": "host_a", "text": "Wait — you're telling me the model was the easy part?"},
    {"speaker": "host_b", "text": "That's exactly what I'm telling you. The hard part was getting anyone to trust it.", "pause_after": -150}
  ]
}
```

```bash
.venv/bin/python produce.py episode.json            # synthesize, upload, rebuild feed
.venv/bin/python produce.py episode.json --dry-run  # render to out/ only, no upload
```

`speaker` is `host_a` / `host_b` (configured in `config.toml`). Optional per-turn
knobs: `pause_after` (ms to the next turn; **negative overlaps** them), `speed`,
`gain_db`. Inline, inside `text`: `[pause]` / `[pause:700]` for a beat, `[breath]`
for an inhale, and `[word](/ˈɪpə/)` to hand-set a pronunciation. The point is two
distinct people reacting to each other — not one explanation split across two
voices. `CLAUDE.md` has the why and the craft.

## Configuration

- **`config.toml`** — podcast metadata, and the two hosts: each is a `name`, a
  Kokoro `voice` (`am_`/`af_` = US male/female, `bm_`/`bf_` = UK; full
  [voice list](https://github.com/hexgrad/kokoro)), a stereo `pan`, and a `persona`
  that steers how Claude writes that character. The `[tts]` block tunes pacing,
  per-turn variation, the mic/room-tone realism layer, and mastering loudness — each
  field is commented.
- **`pronunciations.toml`** — a `term → IPA` dictionary auto-applied to every script,
  so recurring jargon and names come out right without per-script annotation. Add
  only terms the model actually says wrong; verify with `tools/check_pron.py`.

## Hosting

`storage.py` is plain S3 (`boto3`). To use a provider other than R2, point `.env` at
it — `R2_ENDPOINT`, the keys, `R2_BUCKET`, the public `R2_PUBLIC_URL_BASE`, and
`R2_REGION` (`auto` for R2; the bucket's real region for AWS S3). The bucket must
serve its objects publicly so podcast apps can fetch them.

**No object storage at all?** `produce.py --dry-run` writes the finished `feed.xml`
and MP3s to `out/` — host that folder on any static host (GitHub Pages, Netlify,
your own server). Set `R2_PUBLIC_URL_BASE` to where you'll serve it so the feed's
links resolve; the other `R2_*` vars can stay as placeholders in dry-run.

## Tests

```bash
.venv/bin/pytest -q
```

`test_storage_integration.py` is the only one that hits live storage (your `.env`);
deselect it with `--deselect tests/test_storage_integration.py` to run offline.

## License

MIT — see [LICENSE](LICENSE).
