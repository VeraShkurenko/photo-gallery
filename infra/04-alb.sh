#!/usr/bin/env bash
# Етап 6. Application Load Balancer + target group з health check /health (И5).
set -euo pipefail
cd "$(dirname "$0")"; source config.sh
# ALB потребує дві підмережі в різних AZ: підмережа web (us-east-1c) + us-east-1a
WEB_SUBNET=$(aws ec2 describe-instances --instance-ids $WEB1_ID --query 'Reservations[0].Instances[0].SubnetId' --output text)
SUBNET_A=$(aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC_ID Name=availability-zone,Values=us-east-1a --query 'Subnets[0].SubnetId' --output text)

TG_ARN=$(aws elbv2 describe-target-groups --names $TG_NAME --query 'TargetGroups[0].TargetGroupArn' --output text 2>/dev/null || \
  aws elbv2 create-target-group --name $TG_NAME --protocol HTTP --port 80 --vpc-id $VPC_ID --target-type instance \
    --health-check-protocol HTTP --health-check-path /health --matcher HttpCode=200 \
    --health-check-interval-seconds 15 --healthy-threshold-count 2 --unhealthy-threshold-count 2 \
    --query 'TargetGroups[0].TargetGroupArn' --output text)
aws elbv2 register-targets --target-group-arn $TG_ARN --targets Id=$WEB1_ID Id=$WEB2_ID

ALB_ARN=$(aws elbv2 describe-load-balancers --names $ALB_NAME --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null || \
  aws elbv2 create-load-balancer --name $ALB_NAME --type application --scheme internet-facing \
    --subnets $WEB_SUBNET $SUBNET_A --security-groups $ALB_SG \
    --query 'LoadBalancers[0].LoadBalancerArn' --output text)
[ "$(aws elbv2 describe-listeners --load-balancer-arn $ALB_ARN --query 'length(Listeners)' --output text)" = "0" ] && \
  aws elbv2 create-listener --load-balancer-arn $ALB_ARN --protocol HTTP --port 80 \
    --default-actions Type=forward,TargetGroupArn=$TG_ARN >/dev/null
aws elbv2 wait load-balancer-available --load-balancer-arns $ALB_ARN
aws elbv2 wait target-in-service --target-group-arn $TG_ARN --targets Id=$WEB1_ID Id=$WEB2_ID
aws elbv2 describe-target-health --target-group-arn $TG_ARN \
  --query 'TargetHealthDescriptions[].[Target.Id,TargetHealth.State]' --output text
echo "ALB DNS: http://$(aws elbv2 describe-load-balancers --load-balancer-arns $ALB_ARN --query 'LoadBalancers[0].DNSName' --output text)/"
