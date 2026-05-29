import os
import textwrap
import config as cfg


def test_load_config_reads_toml_and_env(tmp_path, monkeypatch):
    toml = tmp_path / "config.toml"
    toml.write_text(textwrap.dedent("""
        [podcast]
        title = "Earful"
        description = "desc"
        author = "Me"
        email = "me@example.com"

        [voices]
        host_a = "am_michael"
        host_b = "af_heart"

        [tts]
        model = "mlx-community/Kokoro-82M-bf16"
        pause_ms = 400
        sample_rate = 24000
    """))
    for k in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_URL_BASE"):
        monkeypatch.setenv(k, f"val-{k}")
    monkeypatch.setenv("R2_PUBLIC_URL_BASE", "https://pub-x.r2.dev/")

    c = cfg.load_config(toml_path=str(toml), env_path="/nonexistent")

    assert c.podcast.title == "Earful"
    assert c.podcast.explicit is False
    assert c.voices["host_a"] == "am_michael"
    assert c.speed == 1.05  # slightly-faster default when unset
    assert c.sentence_pause_ms == 160
    assert c.pause_min_ms == -100 and c.pause_max_ms == 500  # organic-variation defaults
    assert c.gain_jitter_db == 2.0
    assert c.drift_db == 1.5 and c.room_tone_db == -50.0 and c.mic_chain is True
    assert c.r2.bucket == "val-R2_BUCKET"
    assert c.r2.public_base == "https://pub-x.r2.dev"  # trailing slash stripped
    # [voices] fallback: hosts derived with name == id, empty persona
    assert c.hosts["host_a"].name == "host_a"
    assert c.hosts["host_a"].voice == "am_michael"


def test_load_config_reads_host_personas(tmp_path, monkeypatch):
    toml = tmp_path / "config.toml"
    toml.write_text(textwrap.dedent("""
        [podcast]
        title = "Earful"
        description = "d"
        author = "Me"
        email = "me@example.com"

        [hosts.host_a]
        name = "Theo"
        voice = "am_puck"
        persona = "curious driver"

        [hosts.host_b]
        name = "Mara"
        voice = "af_heart"
        persona = "seasoned expert"
    """))
    for k in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_URL_BASE"):
        monkeypatch.setenv(k, "x")
    c = cfg.load_config(toml_path=str(toml), env_path="/nonexistent")
    assert c.hosts["host_a"].name == "Theo"
    assert c.hosts["host_a"].persona == "curious driver"
    assert c.voices == {"host_a": "am_puck", "host_b": "af_heart"}  # derived for tts


def test_load_config_missing_env_raises(tmp_path, monkeypatch):
    toml = tmp_path / "config.toml"
    toml.write_text('[podcast]\ntitle="t"\ndescription="d"\nauthor="a"\nemail="e"\n[voices]\nhost_a="am_michael"\nhost_b="af_heart"\n')
    for k in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_URL_BASE"):
        monkeypatch.delenv(k, raising=False)
    import pytest
    with pytest.raises(RuntimeError):
        cfg.load_config(toml_path=str(toml), env_path="/nonexistent")
