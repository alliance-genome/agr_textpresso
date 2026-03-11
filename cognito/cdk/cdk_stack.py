from aws_cdk import (
    Stack,
    CfnOutput,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_actions as elbv2_actions,
    aws_elasticloadbalancingv2_targets as elbv2_targets,
    aws_cognito as cognito,
    aws_certificatemanager as acm,
)
from constructs import Construct


class CdkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- Replace these with your actual values ---
        EXISTING_ALB_ARN = "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-alb/1234567890"
        EXISTING_ALB_SG_ID = "sg-12345678"
        EXISTING_VPC_ID = "vpc-12345678"
        EXISTING_CERTIFICATE_ARN = "arn:aws:acm:us-east-1:123456789012:certificate/abcd-1234"
        EXISTING_INSTANCE_IDS = [
            "i-0123456789abcdef0",
            "i-0123456789abcdef1",
            "i-0123456789abcdef2",
            "i-0123456789abcdef3",
            "i-0123456789abcdef4",
        ]
        COGNITO_DOMAIN_PREFIX = "cdk-alb-auth"  # must be globally unique
        CALLBACK_DOMAIN = "your-alb-domain.example.com"
        # ---------------------------------------------

        # Import existing VPC
        vpc = ec2.Vpc.from_lookup(self, "Vpc",
            vpc_id=EXISTING_VPC_ID,
        )

        # Import existing ALB
        alb_sg = ec2.SecurityGroup.from_security_group_id(self, "AlbSg", EXISTING_ALB_SG_ID)

        alb = elbv2.ApplicationLoadBalancer.from_application_load_balancer_attributes(self, "ALB",
            load_balancer_arn=EXISTING_ALB_ARN,
            security_group_id=EXISTING_ALB_SG_ID,
            vpc=vpc,
        )

        # Import existing TLS certificate
        certificate = acm.Certificate.from_certificate_arn(self, "Certificate", EXISTING_CERTIFICATE_ARN)

        # Cognito User Pool
        user_pool = cognito.UserPool(self, "UserPool",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=False,
            ),
        )

        # Cognito User Pool Domain (required for ALB auth)
        user_pool_domain = user_pool.add_domain("UserPoolDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=COGNITO_DOMAIN_PREFIX,
            ),
        )

        # Cognito User Pool Client
        user_pool_client = user_pool.add_client("UserPoolClient",
            generate_secret=True,
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
                callback_urls=[f"https://{CALLBACK_DOMAIN}/oauth2/idpresponse"],
            ),
        )

        # Target group with existing EC2 instances
        target_group = elbv2.ApplicationTargetGroup(self, "TargetGroup",
            vpc=vpc,
            port=80,
            target_type=elbv2.TargetType.INSTANCE,
            health_check=elbv2.HealthCheck(path="/"),
            targets=[
                elbv2_targets.InstanceIdTarget(instance_id)
                for instance_id in EXISTING_INSTANCE_IDS
            ],
        )

        # HTTPS listener with Cognito authentication
        https_listener = alb.add_listener("HttpsListener",
            port=443,
            certificates=[certificate],
            default_action=elbv2_actions.AuthenticateCognitoAction(
                user_pool=user_pool,
                user_pool_client=user_pool_client,
                user_pool_domain=user_pool_domain,
                next=elbv2.ListenerAction.forward([target_group]),
            ),
        )

        # HTTP listener — redirect to HTTPS
        alb.add_listener("HttpListener",
            port=80,
            default_action=elbv2.ListenerAction.redirect(
                protocol="HTTPS",
                port="443",
                permanent=True,
            ),
        )

        # Outputs
        CfnOutput(self, "UserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=user_pool_client.user_pool_client_id)
