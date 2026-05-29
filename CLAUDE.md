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
- TTS is isolated behind `tts.synthesize(episode, config)` — swapping engines is a
  single-file change.
- `verify_r2.py` re-checks R2 connectivity if publishing fails.
- The feed lives at `<R2_PUBLIC_URL_BASE>/feed.xml`; the user subscribes their
  podcast app to it once.
