import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Podcast:
    title: str
    description: str
    author: str
    email: str
    language: str
    explicit: bool
    category: str
    link: str


@dataclass(frozen=True)
class R2Creds:
    endpoint: str
    access_key_id: str
    secret_access_key: str
    bucket: str
    public_base: str


@dataclass(frozen=True)
class Config:
    podcast: Podcast
    voices: dict[str, str]
    tts_model: str
    lang_code: str
    pause_min_ms: int
    pause_max_ms: int
    sample_rate: int
    speed: float
    speed_jitter: float
    gain_jitter_db: float
    r2: R2Creds


def load_config(toml_path: str = "config.toml", env_path: str = ".env") -> Config:
    load_dotenv(env_path)
    data = tomllib.loads(Path(toml_path).read_text())
    p = data["podcast"]
    podcast = Podcast(
        title=p["title"],
        description=p["description"],
        author=p["author"],
        email=p["email"],
        language=p.get("language", "en-us"),
        explicit=bool(p.get("explicit", False)),
        category=p.get("category", "Education"),
        link=p.get("link", ""),
    )
    tts = data.get("tts", {})

    def env(key: str) -> str:
        v = os.getenv(key)
        if not v:
            raise RuntimeError(f"Missing required env var: {key} (set it in .env)")
        return v

    r2 = R2Creds(
        endpoint=env("R2_ENDPOINT"),
        access_key_id=env("R2_ACCESS_KEY_ID"),
        secret_access_key=env("R2_SECRET_ACCESS_KEY"),
        bucket=env("R2_BUCKET"),
        public_base=env("R2_PUBLIC_URL_BASE").rstrip("/"),
    )
    return Config(
        podcast=podcast,
        voices=dict(data["voices"]),
        tts_model=tts.get("model", "mlx-community/Kokoro-82M-bf16"),
        lang_code=tts.get("lang_code", "a"),
        pause_min_ms=int(tts.get("pause_min_ms", -100)),  # negative => brief overlap (hosts talk over)
        pause_max_ms=int(tts.get("pause_max_ms", 500)),
        sample_rate=int(tts.get("sample_rate", 24000)),
        speed=float(tts.get("speed", 1.1)),  # 10% faster than Kokoro's 1.0 default
        speed_jitter=float(tts.get("speed_jitter", 0.04)),  # +/- fraction per turn
        gain_jitter_db=float(tts.get("gain_jitter_db", 2.0)),  # +/- dB per turn (mic-distance feel)
        r2=r2,
    )
