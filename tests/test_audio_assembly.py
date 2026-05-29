import numpy as np
import tts
from episode import Episode, Turn


def test_assemble_inserts_silence_between_turns():
    a = np.ones(10, dtype=np.float32)
    b = np.ones(20, dtype=np.float32)
    out = tts.assemble_audio([a, b], [5])
    assert len(out) == 10 + 5 + 20  # no leading/trailing silence
    assert np.all(out[10:15] == 0.0)


def test_assemble_single_turn_has_no_gap():
    a = np.ones(10, dtype=np.float32)
    assert len(tts.assemble_audio([a], [])) == 10


def test_assemble_negative_pause_overlaps_turns():
    a = np.ones(10, dtype=np.float32)
    b = np.ones(20, dtype=np.float32)
    out = tts.assemble_audio([a, b], [-4])  # overlap last 4 of a with first 4 of b
    assert len(out) == 10 + 20 - 4
    assert np.all(out[6:10] == 2.0)  # overlap-add region sums to 2.0


def test_to_int16_scales_and_clips():
    x = np.array([0.0, 1.0, -1.0, 2.0, -2.0], dtype=np.float32)
    out = tts.to_int16(x)
    assert out.dtype == np.int16
    assert out[0] == 0
    assert out[1] == 32767
    assert out[2] == -32767
    assert out[3] == 32767  # clipped
    assert out[4] == -32767  # clipped


def test_apply_gain():
    x = np.ones(4, dtype=np.float32)
    assert np.allclose(tts.apply_gain(x, 0.0), 1.0)
    assert np.allclose(tts.apply_gain(x, 6.0), 1.99526, atol=1e-3)  # +6 dB ~ x2
    assert np.allclose(tts.apply_gain(x, -6.0), 0.50119, atol=1e-3)


def test_episode_seed_is_stable_and_content_derived():
    e1 = Episode("Title", "d", [Turn("host_a", "Hi"), Turn("host_b", "Yo")])
    e2 = Episode("Title", "d", [Turn("host_a", "Hi"), Turn("host_b", "Yo")])
    e3 = Episode("Title", "d", [Turn("host_a", "Hi"), Turn("host_b", "Different")])
    assert tts._episode_seed(e1) == tts._episode_seed(e2)
    assert tts._episode_seed(e1) != tts._episode_seed(e3)


def test_parse_script_extracts_beats_and_breaths():
    assert tts.parse_script("Hello world.", 400) == [("speech", "Hello world.")]
    assert tts.parse_script("Don't buy it. [pause] Why not?", 400) == [
        ("speech", "Don't buy it."), ("pause", 400), ("speech", "Why not?")
    ]
    assert tts.parse_script("Wait [pause:750] for it.", 400) == [
        ("speech", "Wait"), ("pause", 750), ("speech", "for it.")
    ]
    assert tts.parse_script("[pause:300]", 400) == [("pause", 300)]
    assert tts.parse_script("Okay. [breath] So.", 400) == [
        ("speech", "Okay."), ("breath", 0), ("speech", "So.")
    ]


def test_breath_sound_is_short_and_faint():
    b = tts.breath_sound(np.random.default_rng(0), 24000, -28.0)
    assert 0 < len(b) <= 24000  # under a second
    assert 0 < np.max(np.abs(b)) < 0.1  # faint


def test_starts_with_plosive():
    assert tts.starts_with_plosive("Brutal.") is True
    assert tts.starts_with_plosive("'Knew it.") is True  # leading punctuation skipped; K is plosive
    assert tts.starts_with_plosive("Totally.") is True
    assert tts.starts_with_plosive("Honestly, no.") is False
    assert tts.starts_with_plosive('"Exactly."') is False
    assert tts.starts_with_plosive("") is False


def test_add_plosive_only_touches_onset_region():
    mono = np.zeros(24000, dtype=np.float32)
    mono[1000:] = 0.5  # onset at sample 1000
    out = tts.add_plosive(mono, np.random.default_rng(0), 24000, -22.0)
    assert np.array_equal(out[:1000], mono[:1000])  # nothing added before onset
    assert not np.array_equal(out[1000:1100], mono[1000:1100])  # pop mixed in at onset
    assert tts.add_plosive(mono, np.random.default_rng(0), 24000, -130) is not None  # disabled path safe


def test_split_sentences_keeps_abbreviations_intact():
    assert tts.split_sentences("Huh. Okay, but here's the thing.") == ["Huh.", "Okay, but here's the thing."]
    # periods inside A.I. and trailing punctuation must not over-split
    assert tts.split_sentences("It's applied A.I., basically.") == ["It's applied A.I., basically."]
    assert tts.split_sentences("Wait, really? Yeah.") == ["Wait, really?", "Yeah."]
    assert tts.split_sentences("") == []


def test_pan_stereo_positions():
    mono = np.ones(8, dtype=np.float32)
    center = tts.pan_stereo(mono, 0.0)
    assert center.shape == (8, 2)
    assert np.allclose(center[:, 0], center[:, 1])  # equal L/R when centered
    left = tts.pan_stereo(mono, -1.0)
    assert np.allclose(left[:, 1], 0.0) and np.all(left[:, 0] > 0)  # hard left: silent right
    right = tts.pan_stereo(mono, 1.0)
    assert np.allclose(right[:, 0], 0.0) and np.all(right[:, 1] > 0)


def test_assemble_stereo_with_overlap():
    a = np.ones((10, 2), dtype=np.float32)
    b = np.ones((20, 2), dtype=np.float32)
    out = tts.assemble_audio([a, b], [-4])
    assert out.shape == (10 + 20 - 4, 2)
    assert np.all(out[6:10] == 2.0)  # overlap-add region


def test_apply_drift_bounded_and_reproducible():
    mono = np.ones(2000, dtype=np.float32)
    d1 = tts.apply_drift(mono, np.random.default_rng(7), 1.5)
    d2 = tts.apply_drift(mono, np.random.default_rng(7), 1.5)
    assert len(d1) == 2000
    assert np.allclose(d1, d2)  # same seed -> same envelope
    assert d1.max() <= 10 ** (1.5 / 20) + 1e-6  # within +/- max_db
    assert tts.apply_drift(mono, np.random.default_rng(7), 0.0) is not None  # disabled path safe


def test_add_room_tone_adds_faint_energy_and_can_disable():
    silence = np.zeros((1000, 2), dtype=np.float32)
    toned = tts.add_room_tone(silence, np.random.default_rng(1), -50.0)
    assert toned.shape == (1000, 2)
    assert 0 < np.max(np.abs(toned)) < 0.05  # audible-but-faint floor
    assert np.array_equal(tts.add_room_tone(silence, np.random.default_rng(1), -130), silence)  # disabled
