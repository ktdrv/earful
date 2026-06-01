# Earful — how to make an episode

When the user gives a topic ("make an episode about X"): ask a few calibration
questions first (step 0), then do everything else one-shot — no more check-ins
until it's published.

## 0. Calibrate first (the only time you stop to ask)
A bare topic doesn't tell you where to pitch the episode or what tension will make
it sing, so ask me a few quick questions via AskUserQuestion BEFORE researching —
then run straight through research → script → produce without stopping again. Ask:
- **My familiarity with THIS topic** (new to me / solid basics / deep) — sets where
  the conversation starts and how much it can assume.
- **Angle / focus** — which facet of a broad topic to chase, or the question I want
  the episode to actually answer.
- **Tone / format** — e.g. debate-heavy vs. exploratory, rigorous vs. playful.
Skip any I already pinned in my prompt; don't ask about length unless I raise it
(default ~15 min). Those are the ONLY questions — everything after is one-shot.

### Default audience: a smart, informed listener (me)
Unless I say otherwise, assume the listener is an intelligent practitioner who just
may not know THIS particular topic. So: no 101 throat-clearing, no defining obvious
terms, no toy scenarios simplified "for exposition," no explaining-down. Go for real
depth — actual mechanisms, real numbers, genuine tradeoffs, the non-obvious
second-order stuff and the places things break. When in doubt, pitch higher, not
lower. Never be cute at the expense of the listener's intelligence.

## 1. Freshness probe, then research
- Do ONE quick web search to gauge whether my knowledge of the topic is current
  and sufficient.
- If it's solid, write from my own knowledge. If it's stale, thin, or fast-moving,
  do fuller research (search + fetch a few good sources) before writing.

## 2. Write the script to `episode.json`
Two-host conversation between `host_a` and `host_b`. **Each host is a defined
character** — read their `name` and `persona` from `config.toml` under `[hosts.*]`
and write every line in that voice. They are **peers, not teacher-and-student** —
both have done the work and the research, and they meet as equals. They have stable
temperaments but no fixed hierarchy:
- **host_a = Theo** — drives and presses: quick, probing, takes positions and defends
  them, hunts for the mechanism and the spot an argument doesn't hold. Edge and
  energy; shorter, sharper lines. When he asks, it's to pressure-test, not because
  he's lost.
- **host_b = Mara** — complicates and grounds: reaches for the specific case, the
  number, the caveat, the "it's messier than that." Wry, a little unhurried, sits in
  nuance, pushes back when Theo gets too tidy. Thinking alongside, never lecturing.

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
- **They are different people.** Different vocabulary, different instincts, different
  things they get excited about. They're equals — when one knows something the other
  doesn't, it's domain, not rank. Don't let them blur into one neutral narrator, and
  never let either slip into explaining-down.
- **Pick the axis of tension that best fits THIS topic.** Their core temperaments are
  fixed, but what they actually clash or differ over should change episode to episode
  to make the dialogue best — concept vs. real-world evidence, optimist vs. skeptic
  on the thing itself, two different domains colliding, or broad agreement reached by
  very different routes. Choose whatever surfaces the most genuine, intelligent
  disagreement for the subject at hand.
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
- **Fixing pronunciation (do this every script):** recurring jargon and proper nouns are
  handled centrally by `pronunciations.toml` — a `term -> misaki-IPA` dictionary that's
  auto-applied to every script at render time (`tts.apply_pronunciations`). So write those
  words normally ("API", "skua") and the pipeline wraps them. **Before producing, scan the
  finished script for any name/acronym/jargon Kokoro would likely mangle that ISN'T already
  in `pronunciations.toml`, and add it** — verify the entry with `tools/check_pron.py`
  (`--render` to hear it) and only keep overrides where the default is genuinely wrong. For
  a true one-off you don't want in the dict, hand-wrap it inline with the same syntax:
  `[word](/ˈIPA/)`, e.g. `[Kubernetes](/kˈubɚnˌɛtɪs/)` (a manual inline override always wins
  over the dict). Spell out numbers when natural ("twenty twenty five", not "2025").
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
