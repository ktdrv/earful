import numpy as np
import tts


def test_assemble_inserts_silence_between_turns_only():
    a = np.ones(10, dtype=np.float32)
    b = np.ones(20, dtype=np.float32)
    out = tts.assemble_audio([a, b], pause_samples=5)
    assert len(out) == 10 + 5 + 20  # no leading/trailing silence
    assert np.all(out[10:15] == 0.0)


def test_assemble_single_turn_has_no_silence():
    a = np.ones(10, dtype=np.float32)
    assert len(tts.assemble_audio([a], pause_samples=5)) == 10


def test_to_int16_scales_and_clips():
    x = np.array([0.0, 1.0, -1.0, 2.0, -2.0], dtype=np.float32)
    out = tts.to_int16(x)
    assert out.dtype == np.int16
    assert out[0] == 0
    assert out[1] == 32767
    assert out[2] == -32767
    assert out[3] == 32767  # clipped
    assert out[4] == -32767  # clipped
