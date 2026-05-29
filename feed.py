import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape, quoteattr


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s or "episode"


def make_guid(mp3_bytes: bytes) -> str:
    return hashlib.sha256(mp3_bytes).hexdigest()


def rfc822(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt)


def _fmt_duration(secs: int) -> str:
    h, rem = divmod(int(secs), 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


def public_url(base: str, key: str) -> str:
    return f"{base.rstrip('/')}/{key}"


@dataclass
class EpisodeRecord:
    title: str
    description: str
    guid: str
    audio_url: str
    length_bytes: int
    duration_secs: int
    pubdate: str


def manifest_to_json(records: list[EpisodeRecord]) -> str:
    return json.dumps([asdict(r) for r in records], indent=2)


def manifest_from_json(text: str) -> list[EpisodeRecord]:
    return [EpisodeRecord(**r) for r in json.loads(text)]


def render_feed(podcast, records: list[EpisodeRecord], public_base: str) -> str:
    cover = public_url(public_base, "cover.png")
    explicit = "yes" if podcast.explicit else "no"
    items = []
    for r in reversed(records):  # manifest stored oldest-first; feed shows newest-first
        items.append(
            "    <item>\n"
            f"      <title>{escape(r.title)}</title>\n"
            f"      <description>{escape(r.description)}</description>\n"
            f'      <enclosure url={quoteattr(r.audio_url)} length="{r.length_bytes}" type="audio/mpeg"/>\n'
            f'      <guid isPermaLink="false">{r.guid}</guid>\n'
            f"      <pubDate>{r.pubdate}</pubDate>\n"
            f"      <itunes:duration>{_fmt_duration(r.duration_secs)}</itunes:duration>\n"
            f"      <itunes:explicit>{explicit}</itunes:explicit>\n"
            "    </item>"
        )
    items_xml = "\n".join(items)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">\n'
        "  <channel>\n"
        f"    <title>{escape(podcast.title)}</title>\n"
        f"    <description>{escape(podcast.description)}</description>\n"
        f"    <language>{escape(podcast.language)}</language>\n"
        f"    <link>{escape(podcast.link or public_base)}</link>\n"
        f"    <itunes:author>{escape(podcast.author)}</itunes:author>\n"
        f"    <itunes:owner><itunes:name>{escape(podcast.author)}</itunes:name>"
        f"<itunes:email>{escape(podcast.email)}</itunes:email></itunes:owner>\n"
        f"    <itunes:image href={quoteattr(cover)}/>\n"
        f"    <itunes:category text={quoteattr(podcast.category)}/>\n"
        f"    <itunes:explicit>{explicit}</itunes:explicit>\n"
        f"{items_xml}\n"
        "  </channel>\n"
        "</rss>\n"
    )
