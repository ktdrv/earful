import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Turn:
    speaker: str
    text: str
    pause_after: int | None = None  # explicit gap (ms) to next turn; negative = overlap


@dataclass(frozen=True)
class Episode:
    title: str
    description: str
    turns: list[Turn]


def load_episode(path: str) -> Episode:
    data = json.loads(Path(path).read_text())
    turns = [Turn(speaker=t["speaker"], text=t["text"], pause_after=t.get("pause_after")) for t in data["turns"]]
    if not turns:
        raise ValueError("episode has no turns")
    return Episode(title=data["title"], description=data["description"], turns=turns)
