#!/usr/bin/env bash
# Етап 1. Мережеві правила (И3, И5) + доступ адміністратора без відкритого SSH.
set -euo pipefail
cd "$(dirname "$0")"; source config.sh

revoke() { aws ec2 revoke-security-group-ingress "$@" >/dev/null 2>&1 && echo "  revoked: $*" || true; }
allow()  { aws ec2 authorize-security-group-ingress "$@" >/dev/null 2>&1 && echo "  added: $*" || echo "  exists: $*"; }

echo "== web-sg: лише HTTP 80 від SG балансувальника; SSH з інтернету закрито"
revoke --group-id $WEB_SG --protocol tcp --port 22 --cidr 0.0.0.0/0
allow  --group-id $WEB_SG --protocol tcp --port 80 --source-group $ALB_SG

echo "== db-sg: MySQL 3306 лише від web-sg; SSH з інтернету закрито"
revoke --group-id $DB_SG --protocol tcp --port 22 --cidr 0.0.0.0/0
allow  --group-id $DB_SG --protocol tcp --port 3306 --source-group $WEB_SG

echo "== alb-sg: HTTP 80 з інтернету"
allow  --group-id $ALB_SG --protocol tcp --port 80 --cidr 0.0.0.0/0

echo "== EC2 Instance Connect Endpoint (безкоштовний) для SSH на db без публічної IP"
EICE_SG=$(aws ec2 describe-security-groups --filters Name=vpc-id,Values=$VPC_ID Name=group-name,Values=eice-sg \
          --query 'SecurityGroups[0].GroupId' --output text)
if [ "$EICE_SG" = "None" ]; then
  EICE_SG=$(aws ec2 create-security-group --group-name eice-sg --vpc-id $VPC_ID \
            --description "EC2 Instance Connect Endpoint (admin SSH to db)" --query GroupId --output text)
  aws ec2 revoke-security-group-egress --group-id $EICE_SG --protocol -1 --cidr 0.0.0.0/0 >/dev/null
  aws ec2 authorize-security-group-egress --group-id $EICE_SG --protocol tcp --port 22 --source-group $DB_SG >/dev/null
fi
allow --group-id $DB_SG --protocol tcp --port 22 --source-group $EICE_SG
EICE=$(aws ec2 describe-instance-connect-endpoints --filters Name=vpc-id,Values=$VPC_ID \
       --query 'InstanceConnectEndpoints[?State!=`delete-complete`]|[0].InstanceConnectEndpointId' --output text)
if [ "$EICE" = "None" ]; then
  aws ec2 create-instance-connect-endpoint --subnet-id $DB_SUBNET --security-group-ids $EICE_SG \
    --tag-specifications "ResourceType=instance-connect-endpoint,Tags=[{Key=Name,Value=eice-${SURNAME}}]" \
    --query 'InstanceConnectEndpoint.InstanceConnectEndpointId' --output text
fi

echo "== Підсумок правил"
for g in $WEB_SG $DB_SG $ALB_SG; do
  aws ec2 describe-security-groups --group-ids $g --query 'SecurityGroups[0].[GroupName, IpPermissions[].[IpProtocol,FromPort,IpRanges[].CidrIp|join(`,`,@),UserIdGroupPairs[].GroupId|join(`,`,@)]]' --output text
done
