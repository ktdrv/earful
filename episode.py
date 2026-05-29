import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Turn:
    speaker: str
    text: str
    pause_after: int | None = None  # explicit gap (ms) to next turn; negative = overlap
    speed: float | None = None      # per-line speed override (deliberate emphasis)
    gain_db: float | None = None    # per-line level override (deliberate emphasis)


@dataclass(frozen=True)
class Episode:
    title: str
    description: str
    turns: list[Turn]


def load_episode(path: str) -> Episode:
    data = json.loads(Path(path).read_text())
    turns = [
        Turn(speaker=t["speaker"], text=t["text"], pause_after=t.get("pause_after"), speed=t.get("speed"), gain_db=t.get("gain_db"))
        for t in data["turns"]
    ]
    if not turns:
        raise ValueError("episode has no turns")
    return Episode(title=data["title"], description=data["description"], turns=turns)
