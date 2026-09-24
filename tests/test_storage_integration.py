import pytest

import config as cfg
from storage import Storage


def test_r2_round_trip():
    # Hits live storage, so it needs a real config.toml and credentials in .env; skip without them.
    try:
        c = cfg.load_config()
    except (FileNotFoundError, RuntimeError) as e:
        pytest.skip(f"no storage configured: {e}")
    s = Storage(c.r2)
    key = "earful-test/storage-it.json"
    url = s.upload_bytes(b'{"ok": true}', key, "application/json")
    assert url == f"{c.r2.public_base}/{key}"
    assert s.download_bytes(key) == b'{"ok": true}'
    assert s.download_bytes("earful-test/does-not-exist.json") is None
    s.delete(key)
    assert s.download_bytes(key) is None
