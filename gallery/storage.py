"""Робота з S3. Облікові дані беруться автоматично з ролі IAM інстансу
(Instance Profile через IMDSv2) — у коді й конфігах ключів немає."""
import boto3
from botocore.config import Config


class S3Storage:
    def __init__(self, bucket, region):
        self.bucket = bucket
        self.client = boto3.client(
            "s3", region_name=region,
            config=Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 2},
                          signature_version="s3v4", s3={"addressing_style": "virtual"}))

    def check(self):
        # реальний запит до S3: чи існує бакет і чи є до нього доступ
        self.client.head_bucket(Bucket=self.bucket)
        return True

    def upload(self, key, data, content_type):
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data,
                               ContentType=content_type)

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def url(self, key, expires=3600):
        # бакет приватний: браузер отримує тимчасове підписане посилання на S3
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires)
