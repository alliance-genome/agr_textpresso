import aws_cdk as core
import aws_cdk.assertions as assertions

from cognito3.cognito3_stack import Cognito3Stack

# example tests. To run these tests, uncomment this file along with the example
# resource in cognito3/cognito3_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = Cognito3Stack(app, "cognito3")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
