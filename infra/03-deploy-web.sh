#!/usr/bin/env bash
# Етапи 4–6. Пакує код, кладе в s3://<bucket>/deploy/ і розгортає на web через SSM Run Command.
# Використання: infra/03-deploy-web.sh [web-1|web-2|all]
set -euo pipefail
cd "$(dirname "$0")"; source config.sh
case "${1:-all}" in web-1) IDS=$WEB1_ID;; web-2) IDS=$WEB2_ID;; *) IDS="$WEB1_ID $WEB2_ID";; esac
cd ..
COPYFILE_DISABLE=1 tar --no-xattrs --exclude .venv --exclude .git --exclude '__pycache__' --exclude .pytest_cache -czf /tmp/gallery.tar.gz \
  gallery wsgi.py requirements.txt deploy schema.sql
aws s3 cp /tmp/gallery.tar.gz s3://$BUCKET/deploy/gallery.tar.gz --only-show-errors
SETUP=$(base64 < deploy/web-setup.sh | tr -d '\n')
for ID in $IDS; do
  CID=$(aws ssm send-command --instance-ids $ID --document-name AWS-RunShellScript --timeout-seconds 900 \
    --parameters "commands=[\"echo $SETUP | base64 -d > /root/web-setup.sh\",\"bash /root/web-setup.sh $BUCKET $AWS_REGION $DB_PRIVATE_IP 2>&1 | tail -15\"]" \
    --query Command.CommandId --output text)
  echo "== $ID ($CID)"
  aws ssm wait command-executed --command-id $CID --instance-id $ID 2>/dev/null || true
  aws ssm get-command-invocation --command-id $CID --instance-id $ID \
    --query '[Status,StandardOutputContent,StandardErrorContent]' --output text
done
