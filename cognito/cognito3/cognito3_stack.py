from aws_cdk import (
    Stack,
    CfnOutput,
    RemovalPolicy,
    aws_cognito as cognito,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_actions as elbv2_actions,
)
from constructs import Construct


# Existing infrastructure references
ALB_LISTENER_ARN = (
    "arn:aws:elasticloadbalancing:us-east-1:100225593120:"
    "listener/app/textpresso-lb/b2971e0d97571691/60855c41adf80549"
)

# Host → (target group ARN, rule priority) mapping
TARGETS = {
    "fb":   ("arn:aws:elasticloadbalancing:us-east-1:100225593120:targetgroup/textpresso-fb/ac49c36bbd5f107b",   96),
    "zfin": ("arn:aws:elasticloadbalancing:us-east-1:100225593120:targetgroup/textpresso-zfin/4076babfbb7710d4", 97),
    "mgi":  ("arn:aws:elasticloadbalancing:us-east-1:100225593120:targetgroup/textpresso-mgi/915f39c875ef9a03",  98),
    "wb":   ("arn:aws:elasticloadbalancing:us-east-1:100225593120:targetgroup/textpresso-wb/e7007468de474433",   99),
    "sgd":  ("arn:aws:elasticloadbalancing:us-east-1:100225593120:targetgroup/textpresso-sgd/cb3bf975e5c3c58b",  100),
}


class Cognito3Stack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ----- Cognito User Pool -----
        user_pool = cognito.UserPool(
            self, "TextpressoUserPool",
            user_pool_name="Textpresso Users",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Cognito domain (required for ALB-Cognito integration)
        user_pool_domain = user_pool.add_domain(
            "TextpressoCognitoDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix="textpresso-auth",
            ),
        )

        # App client for the ALB (needs client secret for ALB integration)
        user_pool_client = user_pool.add_client(
            "TextpressoALBClient",
            user_pool_client_name="textpresso-alb-client",
            generate_secret=True,
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
                callback_urls=[
                    f"https://{name}-textpresso.alliancegenome.org/oauth2/idpresponse"
                    for name in TARGETS.keys()
                ],
            ),
            supported_identity_providers=[
                cognito.UserPoolClientIdentityProvider.COGNITO,
            ],
        )

        # ----- Import existing ALB listener -----
        lb_security_group = ec2.SecurityGroup.from_security_group_id(
            self, "LBSG", "sg-0415cab61ab6b45c5",
        )
        listener = elbv2.ApplicationListener.from_application_listener_attributes(
            self, "ExistingListener",
            listener_arn=ALB_LISTENER_ARN,
            security_group=lb_security_group,
        )

        # ----- Replace listener rules with Cognito auth + forward -----
        for name, (tg_arn, priority) in TARGETS.items():
            host = f"{name}-textpresso.alliancegenome.org"
            target_group = elbv2.ApplicationTargetGroup.from_target_group_attributes(
                self, f"TG-{name}",
                target_group_arn=tg_arn,
            )

            elbv2.ApplicationListenerRule(
                self, f"Rule-{name}",
                listener=listener,
                priority=priority,
                conditions=[
                    elbv2.ListenerCondition.host_headers([host]),
                ],
                action=elbv2_actions.AuthenticateCognitoAction(
                    user_pool=user_pool,
                    user_pool_client=user_pool_client,
                    user_pool_domain=user_pool_domain,
                    next=elbv2.ListenerAction.forward([target_group]),
                ),
            )

        # ----- Outputs -----
        CfnOutput(self, "UserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=user_pool_client.user_pool_client_id)
        CfnOutput(self, "CognitoDomain",
            value=f"https://textpresso-auth.auth.us-east-1.amazoncognito.com",
        )
