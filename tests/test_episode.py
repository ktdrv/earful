import json
import pytest
import episode as ep


def test_load_episode_parses_turns(tmp_path):
    path = tmp_path / "ep.json"
    path.write_text(json.dumps({
        "title": "Intro to X",
        "description": "A primer.",
        "scratchpad": "ignored planning notes",
        "turns": [
            {"speaker": "host_a", "text": "Hello."},
            {"speaker": "host_b", "text": "Hi there."},
        ],
    }))
    e = ep.load_episode(str(path))
    assert e.title == "Intro to X"
    assert e.description == "A primer."
    assert len(e.turns) == 2
    assert e.turns[0].speaker == "host_a"
    assert e.turns[1].text == "Hi there."
    assert e.turns[0].pause_after is None  # optional, absent by default


def test_load_episode_reads_pause_after(tmp_path):
    path = tmp_path / "ep.json"
    path.write_text(json.dumps({
        "title": "t", "description": "d",
        "turns": [
            {"speaker": "host_a", "text": "Boo.", "pause_after": -120},
            {"speaker": "host_b", "text": "Yah."},
        ],
    }))
    e = ep.load_episode(str(path))
    assert e.turns[0].pause_after == -120  # negative -> overlap into next turn


def test_load_episode_empty_turns_raises(tmp_path):
    path = tmp_path / "ep.json"
    path.write_text(json.dumps({"title": "t", "description": "d", "turns": []}))
    with pytest.raises(ValueError):
        ep.load_episode(str(path))
