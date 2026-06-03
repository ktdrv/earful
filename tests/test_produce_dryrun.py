import defusedxml.ElementTree as ET
import numpy as np
import produce
import tts


def test_resolve_episode_path(tmp_path):
    (tmp_path / "ep.md").write_text("x")
    # an explicit existing path is used as-is
    assert produce.resolve_episode_path(str(tmp_path / "ep.md"), "ignored") == str(tmp_path / "ep.md")
    # a bare name resolves against scripts_dir, with or without the .md suffix
    assert produce.resolve_episode_path("ep", str(tmp_path)) == str(tmp_path / "ep.md")
    assert produce.resolve_episode_path("ep.md", str(tmp_path)) == str(tmp_path / "ep.md")


def test_produce_dry_run_writes_local_feed(tmp_path, monkeypatch):
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
        '[tts]\nsample_rate=24000\n'
    )
    for k in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        monkeypatch.setenv(k, "x")
    monkeypatch.setenv("R2_PUBLIC_URL_BASE", "https://pub-x.r2.dev")
    ep = tmp_path / "ep.md"
    ep.write_text("---\ntitle: Test Episode\ndescription: d\n---\nhost_a: Hi.\nhost_b: Hello.\n")

    produce.produce(str(ep), dry_run=True)

    assert (tmp_path / "out" / "feed.xml").exists()
    assert (tmp_path / "out" / "test-episode.mp3").exists()
    xml = (tmp_path / "out" / "feed.xml").read_text()
    ET.fromstring(xml)
    assert "Test Episode" in xml
    assert "https://pub-x.r2.dev/audio/test-episode.mp3" in xml  # stable audio URL
