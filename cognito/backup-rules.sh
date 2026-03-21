#!/bin/bash
# Backup current ALB listener rules before deploying the Cognito stack.
# Run this BEFORE deleting the old rules and deploying.

set -euo pipefail

LISTENER_ARN="arn:aws:elasticloadbalancing:us-east-1:100225593120:listener/app/textpresso-lb/b2971e0d97571691/60855c41adf80549"
BACKUP_FILE="listener-rules-backup.json"

echo "Backing up listener rules..."
aws elbv2 describe-rules --listener-arn "$LISTENER_ARN" > "$BACKUP_FILE"
echo "Saved to $BACKUP_FILE"
echo ""
echo "Rules backed up:"
cat "$BACKUP_FILE" | python3 -c "
import json, sys
rules = json.load(sys.stdin)['Rules']
for r in rules:
    if r['IsDefault']:
        continue
    hosts = [c['Values'][0] for c in r['Conditions'] if c['Field'] == 'host-header']
    print(f\"  Priority {r['Priority']}: {hosts[0] if hosts else 'N/A'}\")
"
echo ""
echo "Next steps:"
echo "  1. Delete the old rules:  ./delete-old-rules.sh"
echo "  2. Deploy the CDK stack:  cdk deploy"
echo "  3. If rollback needed:    ./restore-rules.sh"
