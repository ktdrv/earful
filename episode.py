import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Turn:
    speaker: str
    text: str
    pause_after: int | None = None  # explicit gap (ms) to next turn; negative = overlap
    speed: float | None = None      # per-line speed override
    gain_db: float | None = None    # per-line level override


@dataclass(frozen=True)
class Episode:
    title: str
    description: str
    turns: list[Turn]


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split a leading `---\\n...\\n---` frontmatter block from the body. Only simple
    `key: value` scalars are read (title/description); quotes around the value are stripped.
    Returns ({}, text) when there's no frontmatter."""
    m = re.match(r"^\s*---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip().strip('"').strip("'")
    return meta, m.group(2)


_PAUSE_WORDS = {"beat": 300, "pause": 600, "long pause": 1200}
_OVERRIDE_RE = re.compile(r"\[[^\]]+\]\([^)]*\)")  # [word](/ipa/) — preserve verbatim
_PAREN_RE = re.compile(r"\(([^)]*)\)")
_ELLIPSIS_RE = re.compile(r"…|\.{2,}")


def _paren_to_marker(inner: str) -> str:
    """Map a parenthetical's inner text to an inline marker, or '' to drop it (an
    un-actable wryly like '(dry)' becomes a no-op reading note)."""
    s = inner.strip().lower()
    if s in _PAUSE_WORDS:
        return f"[pause:{_PAUSE_WORDS[s]}]"
    if s == "breath":
        return "[breath]"
    m = re.fullmatch(r"pause:\s*(\d+)", s)
    return f"[pause:{m.group(1)}]" if m else ""


def transform_turn(raw: str) -> tuple[str, int | None, float | None]:
    """Translate one turn's raw script text into (spoken text with inline [pause:N]/[breath]
    markers, pause_after, speed). Leading (faster)/(slower) -> speed; a trailing em-dash ->
    overlap into the next turn; ellipsis runs -> a fixed beat; pronunciation overrides kept."""
    raw = raw.strip()
    raw = re.sub(r"^\s*(?:—|--)\s*", "", raw)  # leading interruption dash -> cosmetic
    speed: float | None = None
    m = re.match(r"^\((faster|slower)\)\s*", raw, re.IGNORECASE)
    if m:
        speed = 1.1 if m.group(1).lower() == "faster" else 0.9
        raw = raw[m.end():]
    pause_after: int | None = None
    if re.search(r"(?:—|--)\s*$", raw):
        pause_after = -150
        raw = re.sub(r"\s*(?:—|--)\s*$", "", raw)
    # Stash pronunciation overrides so their (/ipa/) isn't eaten as a parenthetical.
    saved: list[str] = []
    raw = _OVERRIDE_RE.sub(lambda mt: saved.append(mt.group(0)) or f"\x00{len(saved) - 1}\x00", raw)
    raw = _PAREN_RE.sub(lambda mt: _paren_to_marker(mt.group(1)), raw)
    raw = _ELLIPSIS_RE.sub(" [pause:150] ", raw)  # dots often hug a word; tidy collapses the spaces
    raw = re.sub(r"\x00(\d+)\x00", lambda mt: saved[int(mt.group(1))], raw)
    return re.sub(r"[ \t]+", " ", raw).strip(), pause_after, speed


_CUE_RE = re.compile(r"^\s*\*{0,2}\s*([^:*]{1,40}?)\s*\*{0,2}\s*:\s*\*{0,2}\s*(.*)$")


def parse_markdown(text: str, speaker_ids: dict[str, str]) -> Episode:
    """Parse a Markdown audio-script into an Episode. `speaker_ids` maps lowercased host
    names and ids to host ids. Lines before the first recognized cue are ignored; a cue runs
    until the next cue (continuation lines fold in)."""
    meta, body = split_frontmatter(text)
    raw: list[list[str]] = []
    cur: list[str] | None = None
    for line in body.splitlines():
        m = _CUE_RE.match(line)
        spk = speaker_ids.get(m.group(1).strip().lower()) if m else None
        if spk is not None:
            cur = [spk, m.group(2)]
            raw.append(cur)
        elif cur is not None and line.strip():
            cur[1] += " " + line.strip()
    turns: list[Turn] = []
    for spk, body_text in raw:
        text_, pause_after, speed = transform_turn(body_text)
        if text_ or pause_after is not None:
            turns.append(Turn(speaker=spk, text=text_, pause_after=pause_after, speed=speed))
    if not turns:
        raise ValueError("episode has no turns")
    return Episode(title=meta.get("title", ""), description=meta.get("description", ""), turns=turns)


def speaker_ids_from_hosts(hosts: dict) -> dict[str, str]:
    """Build the cue resolver: each host id and its (lowercased) name -> host id."""
    ids = {hid.lower(): hid for hid in hosts}
    ids.update({h.name.lower(): hid for hid, h in hosts.items() if getattr(h, "name", "")})
    return ids


def load_episode(path: str, hosts: dict) -> Episode:
    return parse_markdown(Path(path).read_text(), speaker_ids_from_hosts(hosts))
