"""Show, for every term in pronunciations.toml, what Kokoro's G2P (misaki) says by
DEFAULT versus with our override applied — so you can confirm by eye (phonemes) and,
with --render, by ear (a tiny wav) that each override is actually an improvement.

    .venv/bin/python tools/check_pron.py            # phoneme diff for every entry
    .venv/bin/python tools/check_pron.py --render    # also render out/pron_check.wav

An override only earns its place if DEFAULT is wrong and OVERRIDE is right. If DEFAULT
already sounds correct, delete the entry — a needless override is just another way to
be wrong later. This is the tool that replaces guessing at IPA.
"""
import sys
import tomllib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root, for config/tts
from config import load_config
from tts import apply_pronunciations


def main() -> None:
    render = "--render" in sys.argv
    pron = tomllib.loads(Path("pronunciations.toml").read_text()).get("pronunciations", {})
    if not pron:
        print("pronunciations.toml has no [pronunciations] entries.")
        return

    from misaki import en
    try:
        from misaki import espeak
        g = en.G2P(trf=False, british=False, fallback=espeak.EspeakFallback(british=False))
    except Exception as e:  # espeak missing -> mirrors a stack with no fallback
        print(f"(no espeak fallback: {type(e).__name__}: {e})\n")
        g = en.G2P(trf=False, british=False, fallback=None)

    def phon(text: str) -> str:
        try:
            return g(text)[0]
        except Exception as e:
            return f"<ERR {type(e).__name__}>"

    for term, ipa in pron.items():
        default = phon(term)
        overridden = phon(apply_pronunciations(term, {term: ipa}))
        flag = "  <-- no change (drop it?)" if default == overridden else ""
        print(f"{term}\n  default : {default}\n  override: {overridden}{flag}\n")

    if render:
        cfg = load_config()
        from mlx_audio.tts.utils import load_model
        model = load_model(cfg.tts_model)
        voice = next(iter(cfg.hosts.values())).voice
        # One sentence naming each term, with overrides applied, so you hear them in flow.
        sentence = "Here are the words: " + ", ".join(pron) + "."
        text = apply_pronunciations(sentence, pron)
        chunks = [np.asarray(r.audio, np.float32).reshape(-1)
                  for r in model.generate(text=text, voice=voice, lang_code=cfg.lang_code, speed=cfg.speed)]
        import soundfile as sf
        Path("out").mkdir(exist_ok=True)
        sf.write("out/pron_check.wav", np.concatenate(chunks), cfg.sample_rate)
        print("wrote out/pron_check.wav  (listen: open out/pron_check.wav)")


if __name__ == "__main__":
    main()
