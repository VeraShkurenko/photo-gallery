#!/usr/bin/env bash
# Етап 3. Бакет (И8), ролі IAM без ключів (И7), секрети в SSM Parameter Store (И10),
# S3 Gateway Endpoint (щоб db без інтернету міг класти бекапи в S3, И11).
set -euo pipefail
cd "$(dirname "$0")"; source config.sh
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
TMP=$(mktemp -d)

echo "== Бакет $BUCKET"
aws s3api head-bucket --bucket $BUCKET 2>/dev/null || aws s3api create-bucket --bucket $BUCKET >/dev/null
aws s3api put-public-access-block --bucket $BUCKET --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-ownership-controls --bucket $BUCKET \
  --ownership-controls 'Rules=[{ObjectOwnership=BucketOwnerEnforced}]'
aws s3api put-bucket-encryption --bucket $BUCKET --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
cat > $TMP/bucket-policy.json <<JSON
{ "Version": "2012-10-17", "Statement": [
  { "Sid": "DenyInsecureTransport", "Effect": "Deny", "Principal": "*", "Action": "s3:*",
    "Resource": ["arn:aws:s3:::$BUCKET", "arn:aws:s3:::$BUCKET/*"],
    "Condition": {"Bool": {"aws:SecureTransport": "false"}} } ] }
JSON
aws s3api put-bucket-policy --bucket $BUCKET --policy file://$TMP/bucket-policy.json
# бекапи старші за 30 днів видаляються автоматично
aws s3api put-bucket-lifecycle-configuration --bucket $BUCKET --lifecycle-configuration \
  '{"Rules":[{"ID":"expire-old-backups","Status":"Enabled","Filter":{"Prefix":"backups/"},"Expiration":{"Days":30}}]}'

cat > $TMP/trust.json <<'JSON'
{ "Version": "2012-10-17", "Statement": [ { "Effect": "Allow",
  "Principal": {"Service": "ec2.amazonaws.com"}, "Action": "sts:AssumeRole" } ] }
JSON

make_role() {  # name policy-file
  aws iam get-role --role-name $1 >/dev/null 2>&1 || \
    aws iam create-role --role-name $1 --assume-role-policy-document file://$TMP/trust.json >/dev/null
  aws iam put-role-policy --role-name $1 --policy-name $1-policy --policy-document file://$2
  aws iam attach-role-policy --role-name $1 --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
  aws iam get-instance-profile --instance-profile-name $1 >/dev/null 2>&1 || {
    aws iam create-instance-profile --instance-profile-name $1 >/dev/null
    aws iam add-role-to-instance-profile --instance-profile-name $1 --role-name $1; }
  echo "  роль/профіль $1 готові"
}

echo "== Роль для web: лише свій бакет + читання секретів /gallery/*"
cat > $TMP/web.json <<JSON
{ "Version": "2012-10-17", "Statement": [
  { "Sid": "ListOwnBucket", "Effect": "Allow", "Action": "s3:ListBucket",
    "Resource": "arn:aws:s3:::$BUCKET" },
  { "Sid": "ImagesInOwnBucket", "Effect": "Allow",
    "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
    "Resource": ["arn:aws:s3:::$BUCKET/images/*", "arn:aws:s3:::$BUCKET/deploy/*"] },
  { "Sid": "ReadAppSecrets", "Effect": "Allow", "Action": ["ssm:GetParameter", "ssm:GetParameters"],
    "Resource": "arn:aws:ssm:$AWS_REGION:$ACCOUNT:parameter/gallery/*" } ] }
JSON
make_role $WEB_ROLE $TMP/web.json

echo "== Роль для db: лише запис бекапів у свій бакет + пароль БД"
cat > $TMP/db.json <<JSON
{ "Version": "2012-10-17", "Statement": [
  { "Sid": "WriteBackups", "Effect": "Allow", "Action": "s3:PutObject",
    "Resource": "arn:aws:s3:::$BUCKET/backups/*" },
  { "Sid": "ReadDbPassword", "Effect": "Allow", "Action": "ssm:GetParameter",
    "Resource": "arn:aws:ssm:$AWS_REGION:$ACCOUNT:parameter/gallery/db_password" } ] }
JSON
make_role $DB_ROLE $TMP/db.json
sleep 10  # IAM eventual consistency

attach_profile() {  # instance-id profile
  local assoc cur
  read -r assoc cur < <(aws ec2 describe-iam-instance-profile-associations \
    --filters Name=instance-id,Values=$1 Name=state,Values=associated \
    --query 'IamInstanceProfileAssociations[0].[AssociationId,IamInstanceProfile.Arn]' --output text)
  if [ "$assoc" = "None" ]; then
    aws ec2 associate-iam-instance-profile --instance-id $1 --iam-instance-profile Name=$2 >/dev/null
  elif [[ "$cur" != */$2 ]]; then
    aws ec2 replace-iam-instance-profile-association --association-id $assoc --iam-instance-profile Name=$2 >/dev/null
  fi
  echo "  $1 -> $2"
}
attach_profile $WEB1_ID $WEB_ROLE
attach_profile $WEB2_ID $WEB_ROLE
attach_profile $DB_ID $DB_ROLE

echo "== Секрети в SSM Parameter Store (SecureString), значення генеруються тут і ніде не друкуються"
put_secret() {
  aws ssm get-parameter --name $1 >/dev/null 2>&1 && { echo "  $1 вже існує"; return; }
  aws ssm put-parameter --name $1 --type SecureString --value "$(openssl rand -base64 33 | tr -d '/+=' | cut -c1-32)" >/dev/null
  echo "  $1 створено"
}
put_secret /gallery/db_password
put_secret /gallery/secret_key
put_secret /gallery/admin_password

echo "== S3 Gateway Endpoint (безкоштовний)"
RTB=$(aws ec2 describe-route-tables --filters Name=vpc-id,Values=$VPC_ID Name=association.main,Values=true \
      --query 'RouteTables[0].RouteTableId' --output text)
EP=$(aws ec2 describe-vpc-endpoints --filters Name=vpc-id,Values=$VPC_ID Name=service-name,Values=com.amazonaws.$AWS_REGION.s3 \
     --query 'VpcEndpoints[?State!=`deleted`]|[0].VpcEndpointId' --output text)
[ "$EP" = "None" ] && EP=$(aws ec2 create-vpc-endpoint --vpc-id $VPC_ID --service-name com.amazonaws.$AWS_REGION.s3 \
     --route-table-ids $RTB --query VpcEndpoint.VpcEndpointId --output text)
echo "  $EP ($RTB)"
rm -rf $TMP
