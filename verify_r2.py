"""Verify R2 credentials: put -> get -> public-fetch -> delete a tiny test object.

Run: .venv/bin/python verify_r2.py
Prints PASS/FAIL per step. Never prints secrets.
"""
import os
import sys
import urllib.request

import boto3
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv()

required = ["R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_URL_BASE"]
missing = [k for k in required if not os.getenv(k)]
if missing:
    print(f"FAIL: missing in .env: {', '.join(missing)}")
    sys.exit(1)

bucket = os.environ["R2_BUCKET"]
public_base = os.environ["R2_PUBLIC_URL_BASE"].rstrip("/")
key = "earful-verify.txt"
body = b"earful r2 verification ok"

# R2 is S3-compatible; region must be "auto".
s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["R2_ENDPOINT"],
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    config=Config(region_name="auto", signature_version="s3v4"),
)

def step(label: str, fn) -> None:
    try:
        fn()
        print(f"PASS: {label}")
    except Exception as e:
        print(f"FAIL: {label} -> {type(e).__name__}: {e}")
        sys.exit(1)

step("write object (put_object)", lambda: s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="text/plain"))

def _get() -> None:
    got = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    assert got == body, "round-trip body mismatch"
step("read object back (get_object)", _get)

def _public() -> None:
    # r2.dev rejects the default Python-urllib User-Agent with a 403; real podcast
    # clients send a normal UA, so set one here to mirror their behavior.
    url = f"{public_base}/{key}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        got = r.read()
    assert got == body, "public body mismatch"
step("fetch via public URL (podcast-app path)", _public)

step("delete object (cleanup)", lambda: s3.delete_object(Bucket=bucket, Key=key))

print("\nAll checks passed. R2 is ready for Earful.")
