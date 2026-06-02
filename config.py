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
    """Credentials for any S3-compatible store. Cloudflare R2 is the default (its
    free tier, public dev URL, and zero egress fees fit a public podcast feed), but
    AWS S3, Backblaze B2, DigitalOcean Spaces, Wasabi, and MinIO all speak the same
    API — point `endpoint` at them and set `region`. `region` is "auto" for R2; use
    the bucket's real region for AWS S3."""
    endpoint: str
    access_key_id: str
    secret_access_key: str
    bucket: str
    public_base: str
    region: str


@dataclass(frozen=True)
class Host:
    name: str
    voice: str
    persona: str  # used by the script-authoring step to write this host in character
    pan: float = 0.0  # stereo placement, -1 (left) .. +1 (right)


@dataclass(frozen=True)
class Config:
    podcast: Podcast
    hosts: dict[str, Host]
    voices: dict[str, str]  # derived {host_id: voice}; what tts.synthesize consumes
    tts_model: str
    lang_code: str
    pause_min_ms: int
    pause_max_ms: int
    sentence_pause_ms: int  # gap inserted between sentences within a turn
    beat_pause_ms: int      # default length of a bare inline [pause] marker
    comma_pause_level: int  # comma tokens injected into the phoneme stream to lengthen comma pauses (1 = native Kokoro)
    sample_rate: int
    speed: float
    speed_jitter: float
    gain_jitter_db: float
    drift_db: float       # intra-turn slow level drift (mic-movement feel)
    room_tone_db: float   # faint noise-floor level; <= -120 disables
    breath_db: float      # level of a scripted [breath] inhale
    plosive_db: float     # level of simulated plosive pops; <= -120 disables
    plosive_prob: float   # chance a plosive-initial sentence gets a pop
    mic_chain: bool       # apply the physical-mic tone chain on export
    deess_intensity: float  # de-esser strength (0 disables)
    loudness_lufs: float    # target integrated loudness; > -70 enables loudnorm
    pronunciations: dict[str, str]  # term -> misaki IPA, auto-applied to every script
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

    # Pronunciation overrides live in their own checked-in file (config.toml is gitignored
    # personal config; the pronunciation dict is a shared production asset). term -> IPA in
    # misaki's notation; tts.apply_pronunciations wraps these into the model's input.
    pron_path = Path("pronunciations.toml")
    pronunciations = tomllib.loads(pron_path.read_text()).get("pronunciations", {}) if pron_path.exists() else {}

    # Hosts: prefer the [hosts.*] tables (name + voice + persona). Fall back to a
    # bare [voices] table for backward compatibility (name defaults to the id).
    if "hosts" in data:
        hosts = {hid: Host(name=h["name"], voice=h["voice"], persona=h.get("persona", ""), pan=float(h.get("pan", 0.0))) for hid, h in data["hosts"].items()}
    else:
        hosts = {hid: Host(name=hid, voice=v, persona="") for hid, v in data.get("voices", {}).items()}
    voices = {hid: h.voice for hid, h in hosts.items()}

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
        region=os.getenv("R2_REGION", "auto"),  # "auto" for R2; real region for AWS S3
    )
    return Config(
        podcast=podcast,
        hosts=hosts,
        voices=voices,
        tts_model=tts.get("model", "mlx-community/Kokoro-82M-bf16"),
        lang_code=tts.get("lang_code", "a"),
        pause_min_ms=int(tts.get("pause_min_ms", -100)),  # negative => brief overlap (hosts talk over)
        pause_max_ms=int(tts.get("pause_max_ms", 500)),
        sentence_pause_ms=int(tts.get("sentence_pause_ms", 100)),
        beat_pause_ms=int(tts.get("beat_pause_ms", 400)),
        comma_pause_level=int(tts.get("comma_pause_level", 2)),
        sample_rate=int(tts.get("sample_rate", 24000)),
        speed=float(tts.get("speed", 1.0)),  # 1.0 = Kokoro default; leave it so listener-side playback speed isn't compounded
        speed_jitter=float(tts.get("speed_jitter", 0.04)),  # +/- fraction per turn
        gain_jitter_db=float(tts.get("gain_jitter_db", 2.0)),  # +/- dB per turn (mic-distance feel)
        drift_db=float(tts.get("drift_db", 1.5)),
        room_tone_db=float(tts.get("room_tone_db", -50.0)),
        breath_db=float(tts.get("breath_db", -28.0)),
        plosive_db=float(tts.get("plosive_db", -22.0)),
        plosive_prob=float(tts.get("plosive_prob", 0.4)),
        mic_chain=bool(tts.get("mic_chain", True)),
        deess_intensity=float(tts.get("deess_intensity", 0.4)),
        loudness_lufs=float(tts.get("loudness_lufs", -16.0)),
        pronunciations=pronunciations,
        r2=r2,
    )
