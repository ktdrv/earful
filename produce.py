import argparse
import fcntl
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import config as config_mod
import feed
import tts
from episode import load_episode
from storage import Storage

MANIFEST_KEY = "episodes.json"
FEED_KEY = "feed.xml"
# One render at a time across every checkout/worktree: two concurrent Kokoro loads can
# exhaust this Mac's memory (an unattended morning run may coincide with a manual one).
RENDER_LOCK = Path(tempfile.gettempdir()) / "earful-render.lock"


def resolve_episode_path(arg: str, scripts_dir: str) -> str:
    """An explicit existing path wins; otherwise resolve `<scripts_dir>/<arg>.md`."""
    if Path(arg).exists():
        return arg
    name = arg if arg.endswith(".md") else f"{arg}.md"
    return str(Path(scripts_dir) / name)


def produce(episode_path: str, dry_run: bool, feed_name: str | None = None) -> str:
    cfg = config_mod.load_config()
    # Fail on a typo'd feed name before spending minutes on the render.
    if feed_name and feed_name not in cfg.feeds:
        raise SystemExit(f"No [feeds.{feed_name}] table in config.toml")
    podcast = cfg.feeds[feed_name] if feed_name else cfg.podcast
    # A named feed keeps its manifest, feed and cover under `<name>/`. Audio stays under the
    # shared audio/ prefix; slugs are unique across feeds (daily titles carry the date).
    prefix = f"{feed_name}/" if feed_name else ""
    # Held until this function returns and `lock` is closed; the OS drops it if we crash.
    lock = open(RENDER_LOCK, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Another render is running; try again when it finishes")
    path = resolve_episode_path(episode_path, cfg.scripts_dir)
    episode = load_episode(path, cfg.hosts)
    samples = tts.synthesize(episode, cfg)

    Path("out").mkdir(exist_ok=True)
    slug = feed.slugify(episode.title)
    mp3_path = f"out/{slug}.mp3"
    tags = {"title": episode.title, "artist": podcast.title, "album": podcast.title}
    duration, size = tts.write_mp3(samples, cfg.sample_rate, mp3_path, tags, mic_chain=cfg.mic_chain,
                                   deess_intensity=cfg.deess_intensity, loudness_lufs=cfg.loudness_lufs)

    guid = feed.make_guid(Path(mp3_path).read_bytes())
    # Stable audio key (no content hash) so re-publishing an episode keeps the SAME public
    # URL — a shared link stays valid across re-renders. The feed <guid> still carries the
    # content hash, so podcast apps still detect the update and re-download.
    audio_key = f"audio/{slug}.mp3"
    audio_url = feed.public_url(cfg.r2.public_base, audio_key)
    pubdate = feed.rfc822(datetime.now(timezone.utc))
    record = feed.EpisodeRecord(
        title=episode.title, description=episode.description, guid=guid,
        audio_url=audio_url, length_bytes=size, duration_secs=duration, pubdate=pubdate,
    )
    cover_key = f"{prefix}cover.png"

    if dry_run:
        out_dir = Path("out") / feed_name if feed_name else Path("out")
        out_dir.mkdir(exist_ok=True)
        local = out_dir / "episodes.json"
        manifest = feed.manifest_from_json(local.read_text()) if local.exists() else []
        manifest = [r for r in manifest if feed.slugify(r.title) != feed.slugify(record.title)]  # idempotent re-publish (replace same-title)
        manifest.append(record)
        local.write_text(feed.manifest_to_json(manifest))
        (out_dir / "feed.xml").write_text(feed.render_feed(podcast, manifest, cfg.r2.public_base, cover_key))
        print(f"[dry-run] wrote {mp3_path}, {out_dir}/feed.xml, {out_dir}/episodes.json")
        return f"{out_dir}/feed.xml"

    storage = Storage(cfg.r2)
    storage.upload_file(mp3_path, audio_key, "audio/mpeg")
    raw = storage.download_bytes(prefix + MANIFEST_KEY)
    manifest = feed.manifest_from_json(raw.decode()) if raw else []
    manifest = [r for r in manifest if feed.slugify(r.title) != feed.slugify(record.title)]  # idempotent re-publish (replace same-title)
    manifest.append(record)
    storage.upload_bytes(feed.manifest_to_json(manifest).encode(), prefix + MANIFEST_KEY, "application/json")
    feed_url = storage.upload_bytes(
        feed.render_feed(podcast, manifest, cfg.r2.public_base, cover_key).encode(),
        prefix + FEED_KEY, "application/rss+xml; charset=utf-8",
    )
    print(f"Published: {episode.title}\nFeed: {feed_url}")
    return feed_url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Produce and publish an Earful episode.")
    parser.add_argument("episode", help="episode name (resolved in scripts_dir) or path to a .md script")
    parser.add_argument("--dry-run", action="store_true", help="render locally; skip R2 upload")
    parser.add_argument("--feed", help="publish to the [feeds.<name>] feed from config.toml instead of the main one")
    args = parser.parse_args()
    produce(args.episode, args.dry_run, args.feed)
