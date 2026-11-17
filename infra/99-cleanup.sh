#!/usr/bin/env bash
# ВИДАЛЕННЯ платних ресурсів проєкту ПІСЛЯ перевірки викладачем. Запускати лише свідомо!
# Видаляє: ALB, target group, EC2 Instance Connect Endpoint. Інстанси лише ЗУПИНЯЄ.
# Бакет, ролі, секрети не чіпає (безкоштовні або копійчані) — їх можна видалити в консолі.
set -euo pipefail
cd "$(dirname "$0")"; source config.sh
read -r -p "Точно видалити ALB/target group/EICE і зупинити 3 машини? Введіть yes: " ans
[ "$ans" = "yes" ] || exit 1
ALB_ARN=$(aws elbv2 describe-load-balancers --names $ALB_NAME --query 'LoadBalancers[0].LoadBalancerArn' --output text)
aws elbv2 delete-load-balancer --load-balancer-arn $ALB_ARN
aws elbv2 wait load-balancers-deleted --load-balancer-arns $ALB_ARN
sleep 10
aws elbv2 delete-target-group --target-group-arn $(aws elbv2 describe-target-groups --names $TG_NAME --query 'TargetGroups[0].TargetGroupArn' --output text)
for e in $(aws ec2 describe-instance-connect-endpoints --filters Name=vpc-id,Values=$VPC_ID --query 'InstanceConnectEndpoints[].InstanceConnectEndpointId' --output text); do
  aws ec2 delete-instance-connect-endpoint --instance-connect-endpoint-id $e >/dev/null; done
aws ec2 stop-instances --instance-ids $WEB1_ID $WEB2_ID $DB_ID >/dev/null
echo "Готово."
