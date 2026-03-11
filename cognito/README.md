# Cognito-Authenticated ALB with EC2 Instances

AWS CDK (Python) project that adds Cognito-based authentication to an existing Application Load Balancer and registers existing EC2 instances behind it.

## Architecture

```
                    ┌──────────────┐
   User ──HTTPS──> │  Existing    │
                    │  ALB         │
                    │ (+ Cognito   │
                    │  Auth Action)│
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
         ┌────┴───┐  ┌────┴───┐  ┌────┴───┐
         │  EC2   │  │  EC2   │  │  EC2   │  ... (existing instances)
         │  (i-…) │  │  (i-…) │  │  (i-…) │
         └────────┘  └────────┘  └────────┘
           (Existing Instances)
```

**Imported (existing) resources:**

- **VPC** — Looked up by VPC ID
- **Application Load Balancer** — Imported by ARN and security group
- **ACM Certificate** — Imported by ARN
- **EC2 Instances** — Registered as targets by instance ID

**Created by CDK:**

- **Cognito User Pool** — Email-based sign-in, self-signup, auto-verified email
- **Cognito User Pool Client** — Authorization code grant with OpenID/email/profile scopes
- **Cognito User Pool Domain** — Hosted UI for the authentication flow
- **Target Group** — Registers existing EC2 instances on port 80
- **HTTPS Listener** — Cognito auth action forwarding to target group
- **HTTP Listener** — Redirects to HTTPS

## Prerequisites

- Python 3.12+
- Node.js 18+ (for the CDK CLI)
- AWS CLI configured with valid credentials
- An existing ALB, VPC, ACM certificate, and EC2 instances in your AWS account
- EC2 instances must allow inbound port 80 from the ALB's security group

## Setup

```bash
# Create and activate virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Before deploying, update the constants at the top of `cdk/cdk_stack.py`:

| Constant | What to set |
|---|---|
| `EXISTING_ALB_ARN` | Your ALB's ARN |
| `EXISTING_ALB_SG_ID` | Security group attached to the ALB |
| `EXISTING_VPC_ID` | VPC the ALB lives in |
| `EXISTING_CERTIFICATE_ARN` | ACM certificate ARN already on the ALB |
| `EXISTING_INSTANCE_IDS` | List of EC2 instance IDs to register as targets |
| `COGNITO_DOMAIN_PREFIX` | Globally unique prefix for Cognito hosted UI |
| `CALLBACK_DOMAIN` | Your domain pointing to the ALB |

## Deploy

```bash
# Synthesize CloudFormation template
npx cdk synth

# Review changes
npx cdk diff

# Deploy to AWS
npx cdk deploy
```

After deployment, the stack outputs the User Pool ID and User Pool Client ID.

## Auth Flow

1. User navigates to the ALB URL
2. ALB redirects to the Cognito Hosted UI for sign-in/sign-up
3. User authenticates (email + password)
4. Cognito redirects back to the ALB with an authorization code
5. ALB exchanges the code for tokens and forwards the request to a backend EC2 instance

## Tear Down

```bash
npx cdk destroy
```

## Useful Commands

| Command | Description |
|---|---|
| `npx cdk synth` | Emit the synthesized CloudFormation template |
| `npx cdk deploy` | Deploy the stack to your AWS account/region |
| `npx cdk diff` | Compare deployed stack with current state |
| `npx cdk destroy` | Delete the stack and all resources |
| `npx cdk ls` | List all stacks in the app |
