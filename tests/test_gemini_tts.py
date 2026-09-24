import base64
import io
import json
import urllib.error
import wave

import pytest

import gemini_tts as g
from config import Host
from episode import Turn, parse_markdown


class Cfg:
    gemini_model = "gemini-3.8-flash-tts"
    sample_rate = 24000
    hosts = {"host_a": Host(name="Theo", voice="am_puck", persona="", gemini_voice="Puck"),
             "host_b": Host(name="Mara", voice="af_heart", persona="", gemini_voice="Kore")}


def test_to_gemini_maps_directions_to_tags():
    assert g.to_gemini("a (beat) b") == ("a <short pause> b", None)
    assert g.to_gemini("a (pause) b")[0] == "a <short pause> b"
    assert g.to_gemini("a (long pause) b")[0] == "a <long pause> b"
    assert g.to_gemini("a (pause: 400) b")[0] == "a <short pause> b"
    assert g.to_gemini("a (pause: 1200) b")[0] == "a <long pause> b"
    assert g.to_gemini("a (breath) b")[0] == "a <breath> b"
    assert g.to_gemini("a (laughs) b")[0] == "a <laugh> b"
    assert g.to_gemini("a (the layers) b")[0] == "a b"  # not a tag, mid-line -> dropped


def test_to_gemini_leading_parenthetical_directs_the_turn():
    assert g.to_gemini("(faster) quick point") == ("quick point", "speaking rapidly")
    assert g.to_gemini("(slower) slow point") == ("slow point", "speaking slowly")
    assert g.to_gemini("(dryly) Sure it is.") == ("Sure it is.", "dryly")
    assert g.to_gemini("(beat) Anyway.") == ("<short pause> Anyway.", None)  # a tag, not a style


def test_to_gemini_keeps_dashes_ellipses_and_the_overridden_word():
    assert g.to_gemini("I thought —") == ("I thought —", None)
    assert g.to_gemini("it's about... well, trust.")[0] == "it's about... well, trust."
    assert g.to_gemini("the [skua](/skˈuːə/) bird")[0] == "the skua bird"


def test_parse_markdown_keeps_the_raw_line_for_gemini():
    e = parse_markdown("THEO: (dryly) First. (beat) Second —\nMARA: Sure.\n", {"theo": "host_a", "mara": "host_b"})
    assert e.turns[0].raw == "(dryly) First. (beat) Second —"
    assert e.turns[0].text == "First. [pause:300] Second"  # Kokoro's view is unchanged


def _turns(*sizes: int) -> list[Turn]:
    return [Turn("host_a", "", raw="w " * n) for n in sizes]


def _chunk_words(chunks: list[list[Turn]]) -> list[int]:
    return [sum(len(t.raw.split()) for t in c) for c in chunks]


def test_chunk_turns_balances_chunks_on_turn_boundaries():
    assert _chunk_words(g.chunk_turns(_turns(300, 300, 300), 800)) == [300, 600]
    assert _chunk_words(g.chunk_turns(_turns(100, 100), 800)) == [200]  # fits in one
    assert _chunk_words(g.chunk_turns(_turns(1000), 800)) == [1000]  # an oversized turn still renders, alone
    assert g.chunk_turns([], 800) == []


def test_chunk_turns_never_leaves_a_tiny_last_chunk():
    # Greedy filling would give [790, 17]; a 17-word chunk is mostly padding.
    assert _chunk_words(g.chunk_turns(_turns(400, 390, 15, 2), 800)) == [400, 407]


def test_request_body_is_two_speaker_conversational():
    body = g.request_body([Turn("host_a", "", raw="(dryly) Hi."), Turn("host_b", "", raw="(ignored note)"),
                           Turn("host_b", "", raw="Hello.")], Cfg())
    items = body["input"][0]["content"]
    assert [i["text"] for i in items] == ["Hi.", "Hello."]  # a turn that's only a note is skipped
    assert items[0]["annotations"] == [{"type": "speech_metadata", "speaker": "Theo", "style": "dryly"}]
    assert items[1]["annotations"] == [{"type": "speech_metadata", "speaker": "Mara"}]
    assert body["model"] == "gemini-3.8-flash-tts"
    assert body["generation_config"]["speech_config"] == {
        "mode": "conversational",
        "speakers": [{"speaker": "Theo", "voice": "Puck"}, {"speaker": "Mara", "voice": "Kore"}],
    }


def _response(seconds: float, rate: int = 24000) -> io.BytesIO:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x01\x00" * int(rate * seconds))
    audio = {"type": "audio", "mime_type": "audio/wav", "data": base64.b64encode(buf.getvalue()).decode()}
    return io.BytesIO(json.dumps({"steps": [{"type": "model_output", "content": [audio]}]}).encode())


def _fake_api(monkeypatch, replies: list) -> list:
    """Serve `replies` in order: a float is that many seconds of 24 kHz audio, a (seconds, rate)
    tuple is audio at another rate, an int is an HTTP error status, an exception is raised."""
    calls = []
    def urlopen(req, timeout):
        calls.append(json.loads(req.data))
        r = replies[len(calls) - 1]
        if isinstance(r, Exception):
            raise r
        if isinstance(r, int):
            raise urllib.error.HTTPError(req.full_url, r, "err", {}, io.BytesIO(b"{}"))
        return _response(*r) if isinstance(r, tuple) else _response(r)
    monkeypatch.setattr(g.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(g.time, "sleep", lambda s: None)
    return calls


SIXTY_WORDS = [Turn("host_a", "", raw="one two three four five six seven eight nine ten " * 6)]


def test_render_chunk_returns_pcm(monkeypatch):
    _fake_api(monkeypatch, [21.0])  # 60 words in 21s = 171 wpm
    assert len(g.render_chunk(SIXTY_WORDS, Cfg(), "key")) == 24000 * 21 * 2


def test_render_chunk_retries_server_errors_and_short_audio(monkeypatch):
    # A 503, then audio far too short for the text (skipped content), then a good render.
    calls = _fake_api(monkeypatch, [503, 3.0, 21.0])
    assert len(g.render_chunk(SIXTY_WORDS, Cfg(), "key")) == 24000 * 21 * 2
    assert len(calls) == 3


def test_render_chunk_retries_a_dropped_connection(monkeypatch):
    calls = _fake_api(monkeypatch, [ConnectionResetError("peer reset"), 21.0])
    assert len(g.render_chunk(SIXTY_WORDS, Cfg(), "key")) == 24000 * 21 * 2
    assert len(calls) == 2


def test_render_chunk_rejects_an_unexpected_audio_format(monkeypatch):
    _fake_api(monkeypatch, [(21.0, 44100)] * 3)
    with pytest.raises(RuntimeError, match="expected 24000 Hz mono 16-bit"):
        g.render_chunk(SIXTY_WORDS, Cfg(), "key")


def test_render_chunk_gives_up_after_three_attempts(monkeypatch):
    _fake_api(monkeypatch, [3.0, 3.0, 3.0])
    with pytest.raises(RuntimeError, match="after 3 attempts.*doesn't match the text"):
        g.render_chunk(SIXTY_WORDS, Cfg(), "key")


def test_render_chunk_skips_the_rate_check_for_a_few_words(monkeypatch):
    # "Right, fair." in 3s is 40 wpm, but the model's padding dominates a clip that short.
    _fake_api(monkeypatch, [3.0])
    assert len(g.render_chunk([Turn("host_b", "", raw="Right, fair.")], Cfg(), "key")) == 24000 * 3 * 2


def test_render_chunk_does_not_retry_a_bad_request(monkeypatch):
    calls = _fake_api(monkeypatch, [400, 21.0])
    with pytest.raises(RuntimeError, match="HTTP 400"):
        g.render_chunk(SIXTY_WORDS, Cfg(), "key")
    assert len(calls) == 1


def test_synthesize_joins_chunks_with_a_gap(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setattr(g, "CHUNK_WORDS", 60)
    _fake_api(monkeypatch, [21.0, 21.0])

    class Ep:
        turns = SIXTY_WORDS * 2
    out = g.synthesize(Ep(), Cfg())
    assert len(out) == 24000 * 42 + 24000 * g.CHUNK_GAP_MS // 1000


def test_synthesize_requires_key_and_voices(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        g.synthesize(None, Cfg())
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    cfg = Cfg()
    cfg.hosts = {"host_a": Host(name="Theo", voice="am_puck", persona="")}
    with pytest.raises(RuntimeError, match="gemini_voice"):
        g.synthesize(None, cfg)
