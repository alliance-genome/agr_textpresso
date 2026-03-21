# Cognito3 - Textpresso ALB Authentication

## Project Overview

CDK Python stack that adds Cognito User Pool authentication to the existing `textpresso-lb` Application Load Balancer. This replaces the previous secret-header-based access control with OAuth2/Cognito login.

## Architecture

- **ALB**: `textpresso-lb` (existing, internet-facing, us-east-1)
- **Cognito User Pool**: "Textpresso Users" — self-signup enabled, email sign-in
- **Cognito Domain**: `textpresso-auth.auth.us-east-1.amazoncognito.com`
- **Target Groups**: 5 existing groups (fb, zfin, mgi, wb, sgd), all routing to a single EC2 instance `i-05cafb26fe07db120`
- **Listener Rules**: Host-based routing with `authenticate-cognito` action before forwarding

### Host → Target Group Mapping

| Host | Target Group | Priority |
|------|-------------|----------|
| fb-textpresso.alliancegenome.org | textpresso-fb | 96 |
| zfin-textpresso.alliancegenome.org | textpresso-zfin | 97 |
| mgi-textpresso.alliancegenome.org | textpresso-mgi | 98 |
| wb-textpresso.alliancegenome.org | textpresso-wb | 99 |
| sgd-textpresso.alliancegenome.org | textpresso-sgd | 100 |

## AWS Account

- **Account**: 100225593120
- **Region**: us-east-1
- **VPC**: vpc-55522232

## Commands

```bash
source .venv/bin/activate
pip install -r requirements.txt
cdk synth    # generate CloudFormation template
cdk diff     # preview changes
cdk deploy   # deploy stack
```

## Deployment Workflow

```bash
./backup-rules.sh       # 1. Save current listener rules to listener-rules-backup.json
./delete-old-rules.sh   # 2. Delete old rules (priorities 96-100) — prompts for confirmation
cdk deploy              # 3. Deploy Cognito auth rules
```

## Rollback Workflow

If the deployment doesn't work, restore the previous configuration:

```bash
cdk destroy             # Remove CDK-managed Cognito rules
./restore-rules.sh      # Recreate original secret-header rules from backup
```

## Scripts

- **`backup-rules.sh`** — Exports current listener rules to `listener-rules-backup.json`
- **`delete-old-rules.sh`** — Deletes old rules (refuses to run without a backup)
- **`restore-rules.sh`** — Recreates original rules from `listener-rules-backup.json`

## Deployment Notes

- The existing ALB listener rules (priorities 96-100) use secret-header conditions and are managed outside this stack. They must be **deleted manually** (via `delete-old-rules.sh`) before deploying to avoid priority conflicts.
- The ALB's default action (403 fixed response) is not managed by this stack.
- The User Pool has `RemovalPolicy.RETAIN` to prevent accidental deletion of user data.
- `listener-rules-backup.json` is critical for rollback — do not delete it until the new setup is verified.
