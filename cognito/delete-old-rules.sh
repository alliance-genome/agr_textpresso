#!/bin/bash
# Delete existing listener rules (priorities 96-100) to make way for CDK deployment.
# Run this AFTER backup-rules.sh and BEFORE cdk deploy.

set -euo pipefail

LISTENER_ARN="arn:aws:elasticloadbalancing:us-east-1:100225593120:listener/app/textpresso-lb/b2971e0d97571691/60855c41adf80549"

if [ ! -f "listener-rules-backup.json" ]; then
    echo "ERROR: No backup found. Run ./backup-rules.sh first!"
    exit 1
fi

echo "Fetching current rules..."
RULE_ARNS=$(aws elbv2 describe-rules --listener-arn "$LISTENER_ARN" \
    --query 'Rules[?!IsDefault].RuleArn' --output text)

if [ -z "$RULE_ARNS" ]; then
    echo "No non-default rules found. Nothing to delete."
    exit 0
fi

echo "The following rules will be deleted:"
for arn in $RULE_ARNS; do
    echo "  $arn"
done

read -p "Are you sure? (y/N): " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "Aborted."
    exit 0
fi

for arn in $RULE_ARNS; do
    echo "Deleting $arn ..."
    aws elbv2 delete-rule --rule-arn "$arn"
done

echo "Done. Old rules deleted. You can now run: cdk deploy"
