#!/bin/bash
# Restore the original listener rules from backup.
# Use this if the Cognito deployment doesn't work and you need to roll back.
#
# Steps before running:
#   1. cdk destroy  (or delete the CDK-created rules from the console)
#   2. Run this script

set -euo pipefail

LISTENER_ARN="arn:aws:elasticloadbalancing:us-east-1:100225593120:listener/app/textpresso-lb/b2971e0d97571691/60855c41adf80549"
BACKUP_FILE="listener-rules-backup.json"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file $BACKUP_FILE not found!"
    exit 1
fi

echo "Restoring rules from $BACKUP_FILE ..."

python3 -c "
import json, subprocess, sys

with open('$BACKUP_FILE') as f:
    rules = json.load(f)['Rules']

for rule in rules:
    if rule['IsDefault']:
        continue

    priority = rule['Priority']

    # Build conditions JSON
    conditions = []
    for c in rule['Conditions']:
        if c['Field'] == 'host-header':
            conditions.append({
                'Field': 'host-header',
                'HostHeaderConfig': {'Values': c['HostHeaderConfig']['Values']}
            })
        elif c['Field'] == 'http-header':
            conditions.append({
                'Field': 'http-header',
                'HttpHeaderConfig': {
                    'HttpHeaderName': c['HttpHeaderConfig']['HttpHeaderName'],
                    'Values': c['HttpHeaderConfig']['Values']
                }
            })

    # Build actions JSON
    actions = []
    for a in rule['Actions']:
        if a['Type'] == 'forward':
            tg_arn = a['ForwardConfig']['TargetGroups'][0]['TargetGroupArn']
            actions.append({
                'Type': 'forward',
                'TargetGroupArn': tg_arn
            })

    cmd = [
        'aws', 'elbv2', 'create-rule',
        '--listener-arn', '$LISTENER_ARN',
        '--priority', str(priority),
        '--conditions', json.dumps(conditions),
        '--actions', json.dumps(actions),
    ]

    print(f'Restoring rule priority {priority}...')
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f'  ERROR: {result.stderr.strip()}', file=sys.stderr)
        sys.exit(1)
    else:
        print(f'  OK')

print()
print('All rules restored successfully.')
"
