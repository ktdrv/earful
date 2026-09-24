import fcntl

import defusedxml.ElementTree as ET
import numpy as np
import pytest
import produce
import tts


def test_resolve_episode_path(tmp_path):
    (tmp_path / "ep.md").write_text("x")
    # an explicit existing path is used as-is
    assert produce.resolve_episode_path(str(tmp_path / "ep.md"), "ignored") == str(tmp_path / "ep.md")
    # a bare name resolves against scripts_dir, with or without the .md suffix
    assert produce.resolve_episode_path("ep", str(tmp_path)) == str(tmp_path / "ep.md")
    assert produce.resolve_episode_path("ep.md", str(tmp_path)) == str(tmp_path / "ep.md")


def _dry_run_env(tmp_path, monkeypatch, extra_toml=""):
    # Fake synthesis: ~1.2s of a faint tone (real signal, no model download) so the
    # full mastering chain (de-ess + loudnorm) runs as it would on a real episode.
    def fake_synth(episode, config):
        t = np.linspace(0, 1.2, int(24000 * 1.2), endpoint=False, dtype=np.float32)
        return tts.to_int16(0.1 * np.sin(2 * np.pi * 180 * t))
    monkeypatch.setattr(tts, "synthesize", fake_synth)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        '[podcast]\ntitle="Earful"\ndescription="d"\nauthor="Me"\nemail="me@x.com"\n'
        '[voices]\nhost_a="am_michael"\nhost_b="af_heart"\n'
        '[tts]\nsample_rate=24000\n' + extra_toml
    )
    for k in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        monkeypatch.setenv(k, "x")
    monkeypatch.setenv("R2_PUBLIC_URL_BASE", "https://pub-x.r2.dev")
    ep = tmp_path / "ep.md"
    ep.write_text("---\ntitle: Test Episode\ndescription: d\n---\nhost_a: Hi.\nhost_b: Hello.\n")
    return ep


def test_produce_dry_run_writes_local_feed(tmp_path, monkeypatch):
    ep = _dry_run_env(tmp_path, monkeypatch)

    produce.produce(str(ep), dry_run=True)

    assert (tmp_path / "out" / "feed.xml").exists()
    assert (tmp_path / "out" / "test-episode.mp3").exists()
    xml = (tmp_path / "out" / "feed.xml").read_text()
    ET.fromstring(xml)
    assert "Test Episode" in xml
    assert "https://pub-x.r2.dev/audio/test-episode.mp3" in xml  # stable audio URL


def test_produce_dry_run_named_feed(tmp_path, monkeypatch):
    ep = _dry_run_env(tmp_path, monkeypatch, '[feeds.daily]\ntitle="Earful Daily"\n')

    produce.produce(str(ep), dry_run=True, feed_name="daily")

    xml = (tmp_path / "out" / "daily" / "feed.xml").read_text()
    assert ET.fromstring(xml).find("channel/title").text == "Earful Daily"
    assert "https://pub-x.r2.dev/daily/cover.png" in xml
    assert "https://pub-x.r2.dev/audio/test-episode.mp3" in xml  # audio stays under shared audio/
    assert (tmp_path / "out" / "daily" / "episodes.json").exists()
    assert not (tmp_path / "out" / "feed.xml").exists()  # main feed untouched


def test_produce_refuses_while_another_render_holds_the_lock(tmp_path, monkeypatch):
    ep = _dry_run_env(tmp_path, monkeypatch)
    lock = tmp_path / "render.lock"
    monkeypatch.setattr(produce, "RENDER_LOCK", lock)

    with open(lock, "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)  # stands in for a render in another process
        with pytest.raises(SystemExit, match="Another render is running"):
            produce.produce(str(ep), dry_run=True)
    assert not (tmp_path / "out").exists()

    produce.produce(str(ep), dry_run=True)  # lock released -> renders normally
    assert (tmp_path / "out" / "feed.xml").exists()


def test_produce_unknown_feed_fails_before_rendering(tmp_path, monkeypatch):
    ep = _dry_run_env(tmp_path, monkeypatch)

    with pytest.raises(SystemExit, match=r"\[feeds\.nope\]"):
        produce.produce(str(ep), dry_run=True, feed_name="nope")
    assert not (tmp_path / "out").exists()
