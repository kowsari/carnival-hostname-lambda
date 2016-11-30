# Configures EC2 instance hostnames upon launch. Refer to the README.md for
# more information.
#
# Copyright (c) 2016 Sailthru, Inc., https://www.sailthru.com/
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import re
import time
import json
import boto3

def hostname(event, context):

    # Ensure we have our configuration.
    cfg_r53_zone_id = os.environ['R53_ZONE_ID']
    cfg_tag_env     = os.environ['ENV_TAG']
    cfg_tag_role    = os.environ['ROLE_TAG']

    # Filter out any unwanted events that come through, eg by mistake.
    try:
        if event['source'] != 'aws.ec2':
            print 'Ignorning non-EC2 event'
            return 'Failure'

        if not event['detail']['instance-id']:
            print 'Ignoring event without instance-id'
            return 'Failure'

        if event['detail']['state'] != 'running':
            print 'Ignoring state change as not state == running'
            return 'Failure'

    except Exception as e:
        print 'An unexpected issue occured when parsing the event - possibly corrupt/unexpected event data.'
        raise


    # We have an instance ID. Let's look up the instance and fetch it's full
    # set of information. We get told which region inside the CloudWatch event.
    try:
        # This is horrible, but the problem we have is that the instance gets
        # put into state 'running' before it's had a change to get tagged. So
        # we sleep for a few seconds. Feels horrible given how fast Lambas can
        # be, but is still a tiny fraction of a cost.
        print "Sleeping for 15 seconds for tagging to take place..."
        time.sleep(15)

        print 'Fetching instance data for instance: ' + event['detail']['instance-id']

        client_ec2 = boto3.client('ec2', region_name=event['region'])
        instance_details = client_ec2.describe_instances(
            DryRun=False,
            InstanceIds=[
                event['detail']['instance-id']
            ]
        )['Reservations'][0]['Instances'][0] # Will only ever be one instance returned.

        # Flatten the tag array into a hash/dict
        instance_tags = {}
        for tag in instance_details['Tags']:
            instance_tags[tag['Key']] = tag['Value']

        # We will recieve a cloudwatch event everytime the instance changes to
        # state "running". This will include new instances being launched for
        # the first time, but it will also include instances that have been
        # stopped-started. Therefore, we should check if there is an instance
        # Name tag or not already.

        if 'Name' in instance_tags:
            print 'Instance already tagged, no naming action required.'
            return 'Success'

        # Make sure the tags we need for naming purposes are on the instance. In
        # order for this Lambda to work, these tags need to be added to the
        # instance at launch time by the autoscaling group - user data would be
        # far too late.
        if cfg_tag_env not in instance_tags:
            print 'Required tag ('+ cfg_tag_env +') not found on instance. Unable to name.'
            return 'Failure'

        if cfg_tag_role not in instance_tags:
            print 'Required tag ('+ cfg_tag_role +') not found on instance. Unable to name.'
            return 'Failure'

        # Instance is current unnamed, is in running state and has the source
        # tags we need. Let's generate the hostname!
        #
        # Our naming scheme is regionaz-env-type-unique, but we use some tricks
        # to shorten various details.

        hostname_parts = {}

        # Drop prefix on instance ID
        hostname_parts['instanceid'] = re.sub(r'^i-', '', event['detail']['instance-id'])

        # Grab single char AZ.
        hostname_parts['az'] = instance_details['Placement']['AvailabilityZone'][-1:]

        # Get the region name and create a short version.
        region_split = instance_details['Placement']['AvailabilityZone'][:-1].split('-')
        hostname_parts['region'] = region_split[0] + region_split[1][:1] + region_split[2]

        # We grab first 4 char only, keep names short.
        hostname_parts['environment'] = instance_tags[cfg_tag_env][:4]

        # Role with bad chars replaced
        hostname_parts['role'] = re.sub(r'[_:\s]', '-', instance_tags[cfg_tag_role])

        print hostname_parts

        # Assemble final name
        hostname = hostname_parts['region'] +''+ hostname_parts['az'] +'-'+ hostname_parts['environment'] +'-'+ hostname_parts['role'] +'-'+ hostname_parts['instanceid']
        print "Generated hostname " + hostname + " of length "+ str(len(hostname)) +" chars"


        # We now need to tag our instance with the name that we have generated.
        print "Tagging instance..."

        client_ec2.create_tags(
            DryRun=False,
            Resources=[
                event['detail']['instance-id']
            ],
            Tags=[{
              'Key': 'Name',
              'Value': hostname
            }]
        )




    except Exception as e:
        print 'An unexpected issue occured when querying EC2 for instance details.'
        raise



    return 'Success'
