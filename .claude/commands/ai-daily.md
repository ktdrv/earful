---
description: Research and publish today's ~5-minute AI news brief to the Earful Daily feed
argument-hint: "[--dry-run]"
---

Make today's **AI Daily** episode and publish it, start to finish, without stopping to ask anything. This runs unattended every morning; nobody is watching. Follow the episode playbook in `CLAUDE.md` — hosts, voice, write-for-the-ear rules, pacing syntax, pronunciation — except where this file overrides it.

## Overrides to the playbook

- **Skip step 0 (calibration).** No questions. The audience is the playbook's default: a smart practitioner.
- **Always research.** This replaces the freshness probe; for news your own knowledge is stale by definition.
- **Length: about 5 minutes — 850 to 900 words of dialogue, never more than 900.**
- **Run Python with `uv run --no-project python`**, not the venv path in the playbook (a hook blocks that).

## 1. See what's already been covered

Read `scripts_dir` from `config.toml`. Find the `ai-daily-*.md` files there and read the five most recent. Don't re-cover a story unless there's a material new development, and if so, lead with what's new.

## 2. Research

Run `date` for today's date. The coverage window is the last 48 hours.

Scope is practitioner-focused: model releases and major updates, lab and company news that changes what people can build, developer tools and agents, notable research with code or results people will actually use. Policy, regulation and funding only when they're genuinely big.

Pick 3 to 5 items. For each, **fetch** at least one page — prefer the primary source (the lab's announcement, the paper, the repo, the changelog) — and confirm it's dated inside the window. A search-result snippet alone doesn't count; if you can't fetch a source, drop the item. Nobody reviews this episode before it goes out, so this rule is the only thing between the listener and a wrong claim. Don't state a number you didn't read in a fetched source.

If fewer than 3 news items qualify, fill with notable community projects — open-source releases, interesting repos, tools and demos people are building on the new stuff — held to the same rule: a repo or post you actually opened. Never skip the day.

## 3. Write the script

- **Title:** `AI Daily — <Mon D>: <top story in a few words>`, e.g. `AI Daily — Sep 24: Gemini 4 ships`. The date is required: publishing replaces any existing episode with the same title.
- **File:** `<scripts_dir>/<slug>.md`. The slug is the title lowercased, each run of non-alphanumeric characters turned into one hyphen, leading/trailing hyphens trimmed (the rule in `feed.slugify`) — e.g. `ai-daily-sep-24-gemini-4-ships`.
- **Frontmatter `description`:** one line — a one-sentence summary, then `Links:` and the primary URLs separated by ` · `.
- **Notes** (above the first cue): each item with its headline and source URLs.
- **Shape:** cold open straight into the top story. Per item, one host lands what happened, the other adds why it matters or the catch, and they move on. Brisk, not a debate — the listener will look it up if they want more. Sign off in one line; no recap. Theo and Mara stay in character.
- **Pronunciation:** wrap new names or acronyms Kokoro would likely mangle inline as `[word](/IPA/)`. Do NOT edit `pronunciations.toml` and do NOT run `tools/check_pron.py`.

Count the dialogue words (cue names and parentheticals excluded) and cut to 900 if over.

## 4. Publish

Run `uv run --no-project python produce.py <slug> --feed daily $ARGUMENTS`. If it fails, print the error and stop; don't modify the pipeline to work around it.

Finish by printing the title, the dialogue word count, and the feed URL (or the dry-run path).
