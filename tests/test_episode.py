import pytest
import episode as ep


def test_split_frontmatter_extracts_scalars_and_body():
    meta, body = ep.split_frontmatter('---\ntitle: Hello\ndescription: "a, b: c"\n---\nTHEO: hi\n')
    assert meta == {"title": "Hello", "description": "a, b: c"}
    assert body.strip() == "THEO: hi"


def test_split_frontmatter_none_when_absent():
    meta, body = ep.split_frontmatter("THEO: hi\n")
    assert meta == {} and body == "THEO: hi\n"


def test_transform_parentheticals_to_markers():
    assert ep.transform_turn("a (beat) b")[0] == "a [pause:300] b"
    assert ep.transform_turn("a (pause) b")[0] == "a [pause:600] b"
    assert ep.transform_turn("a (long pause) b")[0] == "a [pause:1200] b"
    assert ep.transform_turn("a (pause: 250) b")[0] == "a [pause:250] b"
    assert ep.transform_turn("a (breath) b")[0] == "a [breath] b"
    assert ep.transform_turn("a (dry) b")[0] == "a b"  # unknown wryly -> dropped


def test_transform_ellipsis_is_fixed_beat_single_period_untouched():
    assert ep.transform_turn("now... knowing")[0] == "now [pause:150] knowing"
    assert ep.transform_turn("now… knowing")[0] == "now [pause:150] knowing"
    assert ep.transform_turn("It's applied A.I., basically.")[0] == "It's applied A.I., basically."


def test_transform_overlap_dash_and_speed():
    text, pause_after, speed = ep.transform_turn("so the cat owns a cat —")
    assert text == "so the cat owns a cat" and pause_after == -150 and speed is None
    text, pause_after, speed = ep.transform_turn("— the cat has a cat.")
    assert text == "the cat has a cat." and pause_after is None
    text, _, speed = ep.transform_turn("(faster) quick point")
    assert text == "quick point" and speed == 1.1
    assert ep.transform_turn("(slower) slow point")[2] == 0.9


def test_transform_preserves_pronunciation_override():
    assert ep.transform_turn("the [skua](/skˈuːə/) bird")[0] == "the [skua](/skˈuːə/) bird"


def test_transform_midtext_emdash_preserved():
    assert ep.transform_turn("the void — and the ceiling")[0] == "the void — and the ceiling"


SPK = {"theo": "host_a", "mara": "host_b", "host_a": "host_a", "host_b": "host_b"}

SCRIPT = """---
title: Demo
description: a demo
---

## Outline (ignored)
- some note

THEO: First line. (beat) Still Theo.
MARA: I jump in —
THEO: — cut off, then more.
Carrying onto a second line.
LedgerBot: not a real host, ignored as prose.
"""


def test_parse_markdown_full():
    e = ep.parse_markdown(SCRIPT, SPK)
    assert e.title == "Demo" and e.description == "a demo"
    assert [t.speaker for t in e.turns] == ["host_a", "host_b", "host_a"]
    assert e.turns[0].text == "First line. [pause:300] Still Theo."
    assert e.turns[1].text == "I jump in" and e.turns[1].pause_after == -150
    assert e.turns[2].text == "cut off, then more. Carrying onto a second line. LedgerBot: not a real host, ignored as prose."


def test_parse_markdown_unknown_first_speaker_means_no_turns():
    with pytest.raises(ValueError):
        ep.parse_markdown("NOBODY: hi\n", SPK)


def test_speaker_ids_from_hosts():
    class H:
        def __init__(self, name): self.name = name
    ids = ep.speaker_ids_from_hosts({"host_a": H("Theo"), "host_b": H("Mara")})
    assert ids == {"host_a": "host_a", "host_b": "host_b", "theo": "host_a", "mara": "host_b"}
