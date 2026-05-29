import os
import numpy as np
import tts


def test_write_mp3_produces_playable_file(tmp_path):
    sr = 24000
    t = np.linspace(0, 1.0, sr, dtype=np.float32)
    tone = (0.2 * np.sin(2 * np.pi * 440 * t))
    samples = tts.to_int16(tone)
    out = tmp_path / "tone.mp3"
    duration, size = tts.write_mp3(samples, sr, str(out), {"title": "Tone", "artist": "Earful"})
    assert out.exists()
    assert size > 0
    assert duration == 1  # ~1 second, rounded
