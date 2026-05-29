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
- Target ~12-18 minutes (~2000-2800 words total across both hosts).
- Open with a brief hook, close with a short recap.

Write for the EAR, not the page — this is the single biggest lever on how natural
it sounds:
- **Use contractions everywhere.** "it's", "you're", "don't", "let's", "we'll",
  "that's", "here's". Never write "let us", "you are", "do not", "it is" — formal
  uninflected phrasing is what makes TTS sound robotic.
- **Sprinkle light discourse markers and fillers**, sparingly: "right", "yeah",
  "I mean", "honestly", "look", "so", "okay so". A little goes a long way.
- **Use short reactive back-channels** between longer turns: "Right." "Exactly."
  "Totally." "Ha, yeah." "Wait, really?" They make it feel like a real exchange.
- **Vary sentence length and rhythm.** Mix a punchy 4-word line with a longer one.
  Don't let every turn be the same shape.
- **Punctuation IS prosody.** Commas = short pauses, periods/ellipses = longer
  beats, question marks = rising intonation, em-dashes = a quick break. Use them
  deliberately to control pacing.
- Keep most sentences under ~20-25 words; the model handles shorter spoken units best.
- **Fixing pronunciation:** for jargon, acronyms, or proper nouns the model mangles,
  use misaki's inline override syntax in the text: `[word](/ˈIPA/)`, e.g.
  `[Kubernetes](/kˈubɚnˌɛtɪs/)`. Spell acronyms with periods to force letter reading
  (e.g. `A.I.`). Spell out numbers when natural ("twenty twenty five", not "2025").
- No stage directions or sound-effect cues inside `text` — only spoken words and the
  override syntax above get read.

Note: the pipeline already adds subtle organic variation automatically (per-turn
speed, level, and pause length, including occasional overlap). Don't try to encode
pauses or emphasis with extra punctuation hacks beyond normal writing.

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
