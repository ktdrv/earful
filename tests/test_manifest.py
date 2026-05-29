import feed


def _rec(title="Ep", guid="g1"):
    return feed.EpisodeRecord(
        title=title, description="d", guid=guid,
        audio_url="https://pub-x.r2.dev/audio/a.mp3",
        length_bytes=123, duration_secs=75, pubdate="Fri, 29 May 2026 12:00:00 +0000",
    )


def test_manifest_round_trip():
    records = [_rec("A", "g1"), _rec("B", "g2")]
    text = feed.manifest_to_json(records)
    back = feed.manifest_from_json(text)
    assert back == records


def test_manifest_from_empty_string_list():
    assert feed.manifest_from_json("[]") == []
