# Textpresso Cognito Authentication

AWS CDK stack that adds Cognito User Pool authentication to the `textpresso-lb` Application Load Balancer, replacing the previous secret-header-based access control with OAuth2/Cognito login.

## What This Stack Creates

- **Cognito User Pool** ("Textpresso Users") with self-signup, email verification, and strong password policy
- **Cognito Hosted UI Domain** at `textpresso-auth.auth.us-east-1.amazoncognito.com`
- **ALB App Client** with OAuth2 authorization code grant and callback URLs for all 5 hosts
- **ALB Listener Rules** (priorities 96-100) with `authenticate-cognito` action before forwarding to existing target groups

### Protected Hosts

| Host | Target Group |
|------|-------------|
| fb-textpresso.alliancegenome.org | textpresso-fb |
| zfin-textpresso.alliancegenome.org | textpresso-zfin |
| mgi-textpresso.alliancegenome.org | textpresso-mgi |
| wb-textpresso.alliancegenome.org | textpresso-wb |
| sgd-textpresso.alliancegenome.org | textpresso-sgd |

## Prerequisites

- Python 3.8+
- AWS CDK CLI (`npm install -g aws-cdk`)
- AWS credentials configured for account `100225593120` (us-east-1)
- Existing ALB listener rules (priorities 96-100) must be deleted before deploying

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Deployment

```bash
# 1. Backup current listener rules
./backup-rules.sh

# 2. Delete old secret-header rules (prompts for confirmation)
./delete-old-rules.sh

# 3. Preview changes
cdk diff

# 4. Deploy the Cognito auth stack
cdk deploy
```

## Rollback

If the deployment doesn't work, restore the previous configuration:

```bash
# 1. Remove CDK-managed resources
cdk destroy

# 2. Recreate original secret-header rules from backup
./restore-rules.sh
```

## Scripts

| Script | Description |
|--------|-------------|
| `backup-rules.sh` | Exports current listener rules to `listener-rules-backup.json` |
| `delete-old-rules.sh` | Deletes old rules (refuses to run without a backup) |
| `restore-rules.sh` | Recreates original rules from backup |

## Stack Outputs

| Output | Description |
|--------|-------------|
| UserPoolId | Cognito User Pool ID |
| UserPoolClientId | App client ID for the ALB |
| CognitoDomain | Cognito hosted UI URL |

## Authentication Flow

1. User visits any of the 5 textpresso hosts
2. ALB redirects unauthenticated users to the Cognito hosted login page
3. User signs up or logs in with email/password
4. Cognito redirects back to the ALB callback URL with an authorization code
5. ALB exchanges the code for tokens and forwards the request to the target group

## Important Considerations

### Cognito Domain Prefix

The domain prefix `textpresso-auth` must be globally unique across all AWS accounts. If deployment fails on this resource, choose a different prefix in `cognito3_stack.py`.

### Programmatic Access

The previous secret-header approach allowed bots, scripts, and services to access the textpresso hosts by sending the `alliance-textpresso-secret` header. Cognito authentication requires a browser-based OAuth flow — any automated clients using the secret header will stop working after deployment.

### Cookie / Header Size Limits

The ALB sets `AWSELBAuthSessionCookie` cookies containing JWT tokens, which can be large. If the textpresso applications also set large cookies or headers, you may hit the ALB's 16KB header size limit, resulting in 400 errors.

### Session Timeout

The default ALB-Cognito session duration is 7 days (604800 seconds). Users won't need to re-authenticate for a week. This can be tuned via the `session_timeout` parameter on `AuthenticateCognitoAction` in `cognito3_stack.py`.

### CORS / AJAX Requests

If the textpresso applications make cross-origin or AJAX requests, the Cognito redirect (302) will not work for those calls — they will fail silently. This only matters if there are frontend API calls between the hosts.

### Self-Signup Is Open

Self-signup is enabled, meaning anyone with an email address can register. To restrict access to specific users or email domains, add a Cognito pre-sign-up Lambda trigger to validate registrations.

### Health Checks

ALB health checks (`/tpc` on port 80) go directly to the target instance, not through listener rules, so Cognito auth will not interfere with them.

## Deployment Notes

- The existing listener rules using `alliance-textpresso-secret` header checks must be removed manually (via `delete-old-rules.sh`) before deploying this stack, as they occupy the same priorities (96-100).
- The ALB default action (403 response) is unchanged and remains as a catch-all for unmatched requests.
- The User Pool has a RETAIN removal policy to protect user data if the stack is destroyed.
- `listener-rules-backup.json` is critical for rollback — do not delete it until the new setup is verified.
