from datetime import datetime, timezone
import feed


def test_slugify():
    assert feed.slugify("Intro to X: Part 1!") == "intro-to-x-part-1"
    assert feed.slugify("") == "episode"


def test_make_guid_is_stable_and_content_derived():
    g1 = feed.make_guid(b"abc")
    g2 = feed.make_guid(b"abc")
    g3 = feed.make_guid(b"xyz")
    assert g1 == g2
    assert g1 != g3
    assert len(g1) == 64  # sha256 hex


def test_rfc822_format():
    dt = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
    s = feed.rfc822(dt)
    assert "29 May 2026" in s
    assert s.endswith("+0000")


def test_fmt_duration():
    assert feed._fmt_duration(75) == "1:15"
    assert feed._fmt_duration(3725) == "1:02:05"


def test_public_url():
    assert feed.public_url("https://pub-x.r2.dev/", "audio/a.mp3") == "https://pub-x.r2.dev/audio/a.mp3"
