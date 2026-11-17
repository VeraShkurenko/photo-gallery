#!/usr/bin/env python3
"""Щоденний бекап БД gallery у S3: mysqldump | gzip -> s3://<bucket>/backups/.
Облікові дані AWS — з ролі IAM інстансу db (ключів немає).
Доступ до S3 — через VPC Gateway Endpoint (у db немає публічної IP)."""
import gzip
import socket
import subprocess
from datetime import datetime, timezone

import boto3

conf = dict(line.strip().split("=", 1) for line in open("/etc/gallery-backup.conf") if "=" in line)
stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
key = f"backups/gallery_{stamp}.sql.gz"

dump = subprocess.run(
    ["mysqldump", "--single-transaction", "--routines", "--triggers", "--databases", "gallery"],
    check=True, capture_output=True).stdout
body = gzip.compress(dump)
boto3.client("s3", region_name=conf["REGION"]).put_object(
    Bucket=conf["BUCKET"], Key=key, Body=body, ContentType="application/gzip")
print(f"backup ok: s3://{conf['BUCKET']}/{key} ({len(body)} bytes) from {socket.gethostname()}")
