import xml.etree.ElementTree as ET  # safe: we only parse our own generated output, never untrusted input
import config as cfg
import feed


def _podcast():
    return cfg.Podcast(
        title="Earful", description="desc", author="Me", email="me@example.com",
        language="en-us", explicit=False, category="Education", link="",
    )


def _rec(title, guid):
    return feed.EpisodeRecord(
        title=title, description="A & B <test>", guid=guid,
        audio_url="https://pub-x.r2.dev/audio/a.mp3",
        length_bytes=999, duration_secs=3725, pubdate="Fri, 29 May 2026 12:00:00 +0000",
    )


def test_render_feed_is_valid_xml_with_essentials():
    xml = feed.render_feed(_podcast(), [_rec("First", "g1")], "https://pub-x.r2.dev")
    root = ET.fromstring(xml)  # raises if malformed; proves escaping works
    assert root.tag == "rss"
    assert "<enclosure" in xml
    assert 'length="999"' in xml
    assert 'type="audio/mpeg"' in xml
    assert "g1" in xml
    assert "1:02:05" in xml  # itunes:duration
    assert "https://pub-x.r2.dev/cover.png" in xml  # channel image


def test_render_feed_newest_first():
    xml = feed.render_feed(_podcast(), [_rec("Old", "g1"), _rec("New", "g2")], "https://pub-x.r2.dev")
    assert xml.index("New") < xml.index("Old")


def test_render_feed_attributes_survive_quotes():
    # A double quote in an attribute-bound field must not break the XML.
    pod = cfg.Podcast(
        title="t", description="d", author="a", email="e@x.com",
        language="en-us", explicit=False, category='Tech "quoted" & <stuff>', link="",
    )
    rec = feed.EpisodeRecord(
        title="T", description="d", guid="g1",
        audio_url='https://pub-x.r2.dev/audio/a".mp3', length_bytes=1, duration_secs=1,
        pubdate="Fri, 29 May 2026 12:00:00 +0000",
    )
    root = ET.fromstring(feed.render_feed(pod, [rec], "https://pub-x.r2.dev"))  # must not raise
    ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
    assert root.find(".//channel/itunes:category", ns).get("text") == 'Tech "quoted" & <stuff>'
    assert root.find(".//item/enclosure").get("url") == 'https://pub-x.r2.dev/audio/a".mp3'
