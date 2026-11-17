#!/usr/bin/env bash
# С24: перевірка з власного комп'ютера, що MySQL і web напряму недоступні.
cd "$(dirname "$0")/.."; source infra/config.sh
echo "Перевірка доступу ззовні — Shkurenko — $(date '+%d.%m.%Y %H:%M:%S')  (мій Mac: $(curl -s -m 5 https://checkip.amazonaws.com))"
DB_PUB=$(aws ec2 describe-instances --instance-ids $DB_ID --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo; echo "db-node-Shkurenko: публічна IP = $DB_PUB, приватна = $DB_PRIVATE_IP"
echo "\$ nc -zv -G 5 $DB_PRIVATE_IP 3306"; nc -zv -G 5 -w 5 $DB_PRIVATE_IP 3306 2>&1 || echo "=> MySQL недоступний"
for ID in $WEB1_ID $WEB2_ID; do
  read -r NAME IP < <(aws ec2 describe-instances --instance-ids $ID --query 'Reservations[0].Instances[0].[Tags[?Key==`Name`]|[0].Value,PublicIpAddress]' --output text)
  echo; echo "== $NAME ($IP)"
  echo "\$ nc -zv -G 5 $IP 3306"; nc -zv -G 5 -w 5 $IP 3306 2>&1 || echo "=> порт 3306 закритий"
  echo "\$ curl -m 5 http://$IP/"; curl -sS -m 5 -o /dev/null -w '%{http_code}\n' http://$IP/ 2>&1 || echo "=> прямий доступ до web закритий"
done
ALB=$(aws elbv2 describe-load-balancers --names $ALB_NAME --query 'LoadBalancers[0].DNSName' --output text)
echo; echo "== Через балансувальник:"; echo "\$ curl http://$ALB/health"; curl -s -m 10 http://$ALB/health; echo
