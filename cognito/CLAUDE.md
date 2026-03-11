# Project: Cognito CDK

AWS CDK Python project that deploys an ALB with Cognito authentication fronting 5 EC2 instances.

## Architecture

- **VPC** with public/private subnets across 3 AZs, 1 NAT gateway
- **Cognito User Pool** with email sign-in, self-signup, email verification
- **Application Load Balancer** (internet-facing) with HTTPS listener using Cognito auth action, HTTP->HTTPS redirect
- **Auto Scaling Group** with 5 t3.micro EC2 instances (Amazon Linux 2023, Apache httpd) in private subnets
- **ACM Certificate** for TLS (DNS validation)

## Project Structure

```
app.py                  # CDK app entrypoint
cdk/cdk_stack.py        # Main stack definition (all resources)
cdk/__init__.py
tests/unit/             # Unit tests
cdk.json                # CDK config and feature flags
requirements.txt        # Python dependencies (aws-cdk-lib, constructs)
```

## Commands

```bash
source .venv/bin/activate          # Activate virtualenv
pip install -r requirements.txt    # Install dependencies
npx cdk synth                      # Synthesize CloudFormation template
npx cdk deploy                     # Deploy stack
npx cdk diff                       # Compare deployed vs local
npx cdk destroy                    # Tear down stack
```

## Before Deploying

Update these placeholders in `cdk/cdk_stack.py`:

1. `domain_prefix` — Cognito domain prefix (must be globally unique)
2. `domain_name` — Your actual domain for the ACM certificate
3. `callback_urls` — Set to `https://<your-domain>/oauth2/idpresponse`

## Conventions

- Language: Python 3.12
- CDK version: aws-cdk-lib >=2.241.0
- One stack (`CdkStack`) containing all resources
- L2 constructs preferred over L1 (Cfn) where available
