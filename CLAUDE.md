# Earful — how to make an episode

When the user gives a topic ("make an episode about X"), do all of this without
stopping for review (one-shot):

## 1. Freshness probe, then research
- Do ONE quick web search to gauge whether my knowledge of the topic is current
  and sufficient.
- If it's solid, write from my own knowledge. If it's stale, thin, or fast-moving,
  do fuller research (search + fetch a few good sources) before writing.

## 2. Write the script to `episode.json`
Two-host conversation between `host_a` and `host_b`. **Each host is a defined
character** — read their `name` and `persona` from `config.toml` under `[hosts.*]`
and write every line in that voice. Currently:
- **host_a = Theo** — curious driver: energy, sharp naive questions, wants concrete
  examples, gently pushes back on hype; shorter punchier lines.
- **host_b = Mara** — seasoned expert: grounds things in specifics/numbers, nuanced,
  occasionally wry; slightly longer structured explanations.

### Two people, not one script (the most important rule)
The failure mode to avoid at all costs: writing one explanation and slicing it
across two voices, where each host just completes the other's thought and passes the
ball. That sounds exactly like what it is — a single essay read aloud by two people.

Instead, write an actual conversation between two people who hold their own points of
view (which may align OR clash):
- **Each host reacts to what the other just said** — agrees and adds, qualifies,
  gets surprised, or pushes back — before introducing anything new. The thread is
  reactive, not a relay race of facts.
- **Give them real stances.** They should sometimes disagree, challenge an
  assumption, or come at it from a different angle ("I'd push back on that," "okay
  but here's what I keep seeing," "that's actually annoying because you're right").
  Let one talk the other out of something.
- **Asymmetry is the point.** One host might monologue for five sentences while the
  other just says "Go on." or "Brutal." Their turn lengths and rhythms should differ.
- **They are different people.** Different vocabulary, different worries, different
  things they get excited about. Theo is the one with skin in the game asking the
  anxious, practical questions; Mara is the one who's seen it and grounds or
  complicates his assumptions. Don't let them blur into one neutral narrator.
- Use callbacks, a cold open mid-thought, light humor, and first names occasionally
  (sparingly). If you could swap who says each line without anyone noticing, you've
  written it wrong.

Schema:
```json
{
  "title": "Concise episode title",
  "description": "1-3 sentence summary shown in the podcast app",
  "scratchpad": "My outline/plan before writing turns (ignored by the pipeline)",
  "turns": [
    {"speaker": "host_a", "text": "...", "pause_after": 250},
    {"speaker": "host_b", "text": "..."}
  ]
}
```

### Scripting pacing (non-speech)
You direct the rhythm, not just the words. Use these sparingly and deliberately —
they're seasoning, not every line:
- **`[pause]` / `[pause:Nms]`** inside `text` — a mid-turn beat. Bare `[pause]` is
  ~400ms; `[pause:700]` sets the length. Great before a punchline or reveal:
  `"Anyone can prompt a model now. [pause:500] Knowing which answer to trust is the rare part."`
  The marker is removed from the spoken audio.
- **`"pause_after": <ms>`** on a turn — the exact gap to the next turn, overriding the
  random one. **Negative = overlap** (the next host starts before this one finishes,
  i.e. talking over / jumping in): `"pause_after": -150`. Use a small positive value
  (200-400) for comic/dramatic timing, negative for interruptions or eager agreement.
- Sentences within a turn already get a short automatic pause; you don't need to
  script those. Only add `[pause]`/`pause_after` where you want a beat that's longer,
  shorter, or an overlap than the default rhythm.
Rules:
- **Let each turn be as long as the thought needs — and vary it hard.** A turn
  might be one word ("Brutal.") or five sentences when a host is making a real
  point. Do NOT chop everything into even, ~equal lines; that's what makes it sound
  like one script read by two voices. (Kokoro auto-chunks long turns at sentence
  boundaries, so length is not a technical concern — keep turns under ~3 sentences
  only if you want zero chance of a faint mid-turn seam.)
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

Lean into imperfection — real conversations aren't tidy:
- **Self-corrections / restarts:** occasionally have a host reframe mid-thought —
  "it's about—well, it's really about trust."
- **Asymmetric turns:** don't keep turns evenly balanced. Let one host run three
  sentences while the other just reacts with "Mm, right." or "Wait, really?"
- **Mild disagreement:** they shouldn't always agree. A little pushback —
  "I'd actually push back on that" — then resolution. Tension reads as real.
- **Callbacks:** reference something said earlier ("like you said about churn…") for
  continuity, as real co-hosts do.
- **Cold open:** start mid-thought or with a beat of banter before the topic proper,
  rather than a formal "Welcome to the show."

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
