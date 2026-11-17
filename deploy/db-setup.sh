#!/usr/bin/env bash
# Налаштування машини db (виконується від root один раз; повторний запуск безпечний).
# Аргументи: <bucket> <region>. Файл schema.sql — поруч зі скриптом.
# Пароль користувача БД береться з SSM Parameter Store і ніде не друкується.
set -euo pipefail
BUCKET=$1; REGION=$2
HERE=$(cd "$(dirname "$0")" && pwd)
export DEBIAN_FRONTEND=noninteractive

apt-get update -q
apt-get install -y -q mysql-server python3-boto3 >/dev/null

PRIVATE_IP=$(TOKEN=$(curl -sX PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60'); \
             curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/local-ipv4)

# MySQL слухає лише приватну адресу (И2); X Protocol вимкнено
cat > /etc/mysql/mysql.conf.d/zz-gallery.cnf <<CNF
[mysqld]
bind-address = ${PRIVATE_IP}
mysqlx = OFF
CNF
systemctl enable mysql >/dev/null
systemctl restart mysql

# схема, тригери, початкові категорії
mysql < "$HERE/schema.sql"

# користувач проєкту з правами лише на базу gallery, вхід лише з приватної мережі VPC (И6)
DB_PASSWORD=$(python3 -c "import boto3; print(boto3.client('ssm', region_name='$REGION').get_parameter(Name='/gallery/db_password', WithDecryption=True)['Parameter']['Value'])")
mysql <<SQL
CREATE USER IF NOT EXISTS 'gallery'@'172.31.%' IDENTIFIED BY '${DB_PASSWORD}';
ALTER USER 'gallery'@'172.31.%' IDENTIFIED BY '${DB_PASSWORD}';
GRANT SELECT, INSERT, UPDATE, DELETE ON gallery.* TO 'gallery'@'172.31.%';
-- адміністратор БД (root) — лише локально через unix-socket, віддалений вхід неможливий
DELETE FROM mysql.user WHERE User = 'root' AND Host NOT IN ('localhost');
DELETE FROM mysql.user WHERE User = '';
DROP DATABASE IF EXISTS test;
FLUSH PRIVILEGES;
SQL
unset DB_PASSWORD

# ---------------------------------------------------- щоденний бекап у S3 (И11)
cat > /etc/gallery-backup.conf <<CONF
BUCKET=${BUCKET}
REGION=${REGION}
CONF
install -m 755 "$HERE/gallery-backup.py" /usr/local/sbin/gallery-backup
install -m 644 "$HERE/gallery-backup.service" /etc/systemd/system/gallery-backup.service
install -m 644 "$HERE/gallery-backup.timer" /etc/systemd/system/gallery-backup.timer
systemctl daemon-reload
systemctl enable --now gallery-backup.timer
echo "db setup done: MySQL on ${PRIVATE_IP}:3306"
