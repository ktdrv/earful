import argparse
from datetime import datetime, timezone
from pathlib import Path

import config as config_mod
import feed
import tts
from episode import load_episode
from storage import Storage

MANIFEST_KEY = "episodes.json"
FEED_KEY = "feed.xml"


def produce(episode_path: str, dry_run: bool) -> str:
    cfg = config_mod.load_config()
    episode = load_episode(episode_path)
    samples = tts.synthesize(episode, cfg)

    Path("out").mkdir(exist_ok=True)
    slug = feed.slugify(episode.title)
    mp3_path = f"out/{slug}.mp3"
    tags = {"title": episode.title, "artist": cfg.podcast.title, "album": cfg.podcast.title}
    duration, size = tts.write_mp3(samples, cfg.sample_rate, mp3_path, tags, mic_chain=cfg.mic_chain,
                                   deess_intensity=cfg.deess_intensity, loudness_lufs=cfg.loudness_lufs)

    guid = feed.make_guid(Path(mp3_path).read_bytes())
    audio_key = f"audio/{slug}-{guid[:8]}.mp3"
    audio_url = feed.public_url(cfg.r2.public_base, audio_key)
    pubdate = feed.rfc822(datetime.now(timezone.utc))
    record = feed.EpisodeRecord(
        title=episode.title, description=episode.description, guid=guid,
        audio_url=audio_url, length_bytes=size, duration_secs=duration, pubdate=pubdate,
    )

    if dry_run:
        local = Path("out/episodes.json")
        manifest = feed.manifest_from_json(local.read_text()) if local.exists() else []
        manifest.append(record)
        local.write_text(feed.manifest_to_json(manifest))
        Path("out/feed.xml").write_text(feed.render_feed(cfg.podcast, manifest, cfg.r2.public_base))
        print(f"[dry-run] wrote {mp3_path}, out/feed.xml, out/episodes.json")
        return "out/feed.xml"

    storage = Storage(cfg.r2)
    storage.upload_file(mp3_path, audio_key, "audio/mpeg")
    raw = storage.download_bytes(MANIFEST_KEY)
    manifest = feed.manifest_from_json(raw.decode()) if raw else []
    manifest.append(record)
    storage.upload_bytes(feed.manifest_to_json(manifest).encode(), MANIFEST_KEY, "application/json")
    feed_url = storage.upload_bytes(
        feed.render_feed(cfg.podcast, manifest, cfg.r2.public_base).encode(),
        FEED_KEY, "application/rss+xml; charset=utf-8",
    )
    print(f"Published: {episode.title}\nFeed: {feed_url}")
    return feed_url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Produce and publish an Earful episode.")
    parser.add_argument("episode_json", help="path to the episode JSON")
    parser.add_argument("--dry-run", action="store_true", help="render locally; skip R2 upload")
    args = parser.parse_args()
    produce(args.episode_json, args.dry_run)
