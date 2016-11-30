# Carnival Hostname Lambda

This lambda listens to AWS CloudWatch events and when a new server is launched:

1. We generate a standard hostname based on tag data.
2. We create a DNS record in Route53.
3. We update the tags on the instance.

To allow instances to lookup what their hostname is, we set a CNAME for each
instance ID. This means we do not need to grant wide-reaching tag lookup rights
to EC2 instances.


# Deployment

We use the serverless framework to deploy the Lambda:

    export ENVIRONMENT=staging
    export R53_ZONE_ID=ZYX321
    serverless deploy --stage $ENVIRONMENT

Change `ENVIRONMENT` to suit, generally most sites will have a `staging` and
`production` convention to allow testing of new versions of the Lambda. Note
that this is *not* the same as Puppet environments, a single Lambda can handle
events for all Puppet environments.

Additionally, we need to associate a cloudwatch event to the Lambda. This is
currently not configurable via the Serverless framework itself.


# Testing

After deploying the Lambda, it can be invoked with the test data with:

     serverless invoke --stage $ENVIRONMENT --function hostname --path event.json





# Contributions

All contributions are welcome via Pull Requests including documentation fixes.


# License

    Copyright (c) 2016 Sailthru, Inc., https://www.sailthru.com/

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
