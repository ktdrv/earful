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
