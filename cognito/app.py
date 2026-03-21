#!/usr/bin/env python3
import aws_cdk as cdk

from cognito3.cognito3_stack import Cognito3Stack

app = cdk.App()
Cognito3Stack(app, "Cognito3Stack",
    env=cdk.Environment(account="100225593120", region="us-east-1"),
)

app.synth()
