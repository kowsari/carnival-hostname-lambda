# Carnival Hostname Lambda

This lambda listens to AWS CloudWatch events and when a new server is launched:

1. We generate a standard hostname based on tag data.
2. We create a DNS record in Route53.
3. We update the tags on the instance.

To allow instances to lookup what their hostname is, we set a CNAME for each
instance ID. This means we do not need to grant wide-reaching tag lookup rights
to EC2 instances.

Requirements are that your EC2 instances are configured to have an environment
tagged in the `Environment` tag and a role/label in the `Role` tag.

TODO: Also need to add a cleanup feature...

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
currently not configurable via the Serverless framework itself. To do this:

1. `AWS Console -> CloudWatch Dashboard`
2. `Events -> Rules`
3. Click `Create rule`
4. Select `Amazon EC2` as the event source. Match specific states `Running.` and
   `Terminated`. Permit `Any instance`.
5. Click `Add target`
6. Select the Lambda to validate against.
7. Keep all other details.
8. Click `Configure details` when done.


TODO: We could probably script the above, but best solution is doing for some
form of native integration into Serverless framework. It might be possible to
use custom CFN resources to do this.


# Testing

After deploying the Lambda, it can be invoked with the test data with:

     serverless invoke --stage $ENVIRONMENT --function hostname --path event.json


# User Data integration

To obtain the hostnames from EC2 instance user-data, the following commands can
be used to obtain the instance ID and then resolve the CNAME target for the
instance ID to get the allocated FQDN.

    AWS_INSTANCE_ID=`curl -s http://169.254.169.254/latest/meta-data/instance-id`
    HOSTNAME=`host ${AWS_INSTANCE_ID}.example.com |sed -n "s/^.*\s\(\S*\)\.\$/\1/p"`

Or if just using the short hostname (no FQDN):

    AWS_INSTANCE_ID=`curl -s http://169.254.169.254/latest/meta-data/instance-id`
    HOSTNAME=`host ${AWS_INSTANCE_ID}.example.com | sed -n "s/^.*\s\(\S*\)\.example\.com\.\$/\1/p"`

Alternatively, if your instances are permitted to describe their own tags, the
non-FQDN hostname is set on the `Name` tag.


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
