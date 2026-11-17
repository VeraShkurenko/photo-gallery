# Спільні змінні для скриптів infra/*.sh  (source infra/config.sh)
# Секретів тут немає.
export AWS_REGION=us-east-1
export AWS_PAGER=""
SURNAME=shkurenko
BUCKET=gallery-${SURNAME}
VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)

iid() { aws ec2 describe-instances --filters "Name=tag:Name,Values=$1" \
          "Name=instance-state-name,Values=pending,running,stopping,stopped" \
          --query 'Reservations[0].Instances[0].InstanceId' --output text; }
sgid() { aws ec2 describe-security-groups --filters Name=vpc-id,Values=$VPC_ID "Name=group-name,Values=$1" \
          --query 'SecurityGroups[0].GroupId' --output text; }

WEB1_ID=$(iid web-1-Shkurenko)
WEB2_ID=$(iid web-2-Shkurenko)
DB_ID=$(iid db-node-Shkurenko)
WEB_SG=$(sgid web-sg)
DB_SG=$(sgid db-sg)
ALB_SG=$(sgid alb-sg)
DB_PRIVATE_IP=$(aws ec2 describe-instances --instance-ids $DB_ID --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text)
DB_SUBNET=$(aws ec2 describe-instances --instance-ids $DB_ID --query 'Reservations[0].Instances[0].SubnetId' --output text)

WEB_ROLE=gallery-web-role-${SURNAME}
DB_ROLE=gallery-db-role-${SURNAME}
ALB_NAME=gallery-alb-${SURNAME}
TG_NAME=gallery-tg-${SURNAME}
