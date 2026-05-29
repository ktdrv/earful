import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError


def _public_url(base: str, key: str) -> str:
    return f"{base.rstrip('/')}/{key}"


class Storage:
    def __init__(self, r2) -> None:
        self._s3 = boto3.client(
            "s3",
            endpoint_url=r2.endpoint,
            aws_access_key_id=r2.access_key_id,
            aws_secret_access_key=r2.secret_access_key,
            config=BotoConfig(region_name="auto", signature_version="s3v4"),
        )
        self._bucket = r2.bucket
        self._base = r2.public_base

    def upload_file(self, path: str, key: str, content_type: str) -> str:
        self._s3.upload_file(path, self._bucket, key, ExtraArgs={"ContentType": content_type})
        return _public_url(self._base, key)

    def upload_bytes(self, data: bytes, key: str, content_type: str) -> str:
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)
        return _public_url(self._base, key)

    def download_bytes(self, key: str) -> bytes | None:
        try:
            return self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None
            raise

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=key)
