#!/usr/bin/env bash
# Відкрити термінал на db (без публічної IP) через EC2 Instance Connect Endpoint.
# Ключів не потрібно: CLI створює тимчасовий ключ на 60 секунд.
cd "$(dirname "$0")"; source config.sh
exec aws ec2-instance-connect ssh --instance-id $DB_ID --connection-type eice --os-user ubuntu
