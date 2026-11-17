#!/usr/bin/env bash
# Розгортання сайту на машині web (від root; повторний запуск = оновлення коду).
# Аргументи: <bucket> <region> <db_private_ip>
# Код береться з s3://<bucket>/deploy/gallery.tar.gz (роль web має доступ лише до свого бакета).
set -euo pipefail
BUCKET=$1; REGION=$2; DB_HOST=$3
export DEBIAN_FRONTEND=noninteractive

command -v python3 >/dev/null && dpkg -s python3-venv >/dev/null 2>&1 || {
  apt-get update -q && apt-get install -y -q python3-venv python3-boto3 mysql-client-core-8.0 >/dev/null; }
dpkg -s python3-boto3 mysql-client-core-8.0 >/dev/null 2>&1 || apt-get install -y -q python3-boto3 mysql-client-core-8.0 >/dev/null
id gallery >/dev/null 2>&1 || useradd --system --home /opt/gallery --shell /usr/sbin/nologin gallery

# 1. код
TMP=$(mktemp -d)
python3 -c "import boto3; boto3.client('s3', region_name='$REGION').download_file('$BUCKET', 'deploy/gallery.tar.gz', '$TMP/g.tgz')"
mkdir -p /opt/gallery
tar -xzf $TMP/g.tgz -C /opt/gallery
rm -rf $TMP
[ -d /opt/gallery/.venv ] || python3 -m venv /opt/gallery/.venv
/opt/gallery/.venv/bin/pip install -q --upgrade pip
/opt/gallery/.venv/bin/pip install -q -r /opt/gallery/requirements.txt
chown -R root:root /opt/gallery && chmod -R go-w /opt/gallery

# 2. секрети: SSM Parameter Store -> /etc/gallery.env (root:root 600, поза репозиторієм)
umask 077
python3 - "$REGION" "$BUCKET" "$DB_HOST" > /etc/gallery.env.new <<'PY'
import sys, boto3
region, bucket, db_host = sys.argv[1:4]
ssm = boto3.client("ssm", region_name=region)
get = lambda n: ssm.get_parameter(Name=n, WithDecryption=True)["Parameter"]["Value"]
print(f"SECRET_KEY={get('/gallery/secret_key')}")
print(f"DB_HOST={db_host}")
print("DB_USER=gallery")
print(f"DB_PASSWORD={get('/gallery/db_password')}")
print("DB_NAME=gallery")
print(f"S3_BUCKET={bucket}")
print(f"AWS_REGION={region}")
print("STUDENT_NAME=Shkurenko")
PY
mv /etc/gallery.env.new /etc/gallery.env
chmod 600 /etc/gallery.env; chown root:root /etc/gallery.env

# 3. systemd-сервіс з автозапуском (И9)
install -m 644 /opt/gallery/deploy/gallery.service /etc/systemd/system/gallery.service
systemctl daemon-reload
systemctl enable gallery.service >/dev/null
systemctl restart gallery.service

# 4. адміністратор сайту (пароль — з Parameter Store, через stdin)
set -a; . /etc/gallery.env; set +a
python3 -c "import boto3; print(boto3.client('ssm', region_name='$REGION').get_parameter(Name='/gallery/admin_password', WithDecryption=True)['Parameter']['Value'])" \
  | (cd /opt/gallery && .venv/bin/python -m gallery.manage create-admin admin)

sleep 3
curl -s -m 10 http://127.0.0.1/health; echo
