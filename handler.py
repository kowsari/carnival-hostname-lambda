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
    cfg_r53_zone_id   = os.environ['R53_ZONE_ID']
    cfg_tag_env       = os.environ['ENV_TAG']
    cfg_tag_role      = os.environ['ROLE_TAG']

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
        raise e


    # We have an instance ID. Let's look up the instance and fetch it's full
    # set of information. We get told which region inside the CloudWatch event.
    client_ec2 = boto3.client('ec2', region_name=event['region'])
    instance_tags = {}

    try:
        print 'Fetching instance data for instance: ' + event['detail']['instance-id']


        for i in range(10):
            try:
                # Fetch EC2 instance details
                instance_details = client_ec2.describe_instances(
                    DryRun=False,
                    InstanceIds=[
                        event['detail']['instance-id']
                    ]
                )['Reservations'][0]['Instances'][0] # Will only ever be one instance returned.

                # Flatten the tag array into a hash/dict
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
                    print 'Required tag ('+ cfg_tag_env +') not found on instance (yet?)'
                    raise KeyError('Tags')

                if cfg_tag_role not in instance_tags:
                    print 'Required tag ('+ cfg_tag_role +') not found on instance (yet?)'
                    raise KeyError('Tags')

                # Catch Max Loop
                if i >= 10:
                    # This should never be possible, unless AWS had some kind of
                    # weird outage.
                    print "Timed out waiting for instance tags to become available"
                    return 'Failure'

            except KeyError as e:
                if e not in ['Tags', cfg_tag_env, cfg_tag_role]:
                    # Sometimes when instances are transistioned from state
                    # "pending" to "running", they have not yet had their
                    # autoscale group tags allocated to them, so they are
                    # tagless. If this happens, we should sleep and retry. To
                    # make things worse, sometimes the tags are partially added,
                    # eg "Environment" might exist, but not "Role" for a short
                    # period.

                    sleeptime = 4
                    print "Required tags not allocated to instance yet, sleeping (" + str(sleeptime) +" seconds)..."
                    time.sleep(sleeptime)
                    continue

            except IndexError as e:
                # Should not normally be possible, but we catch it to make testing
                # more obvious when people are using stale data.
                print "Instance ID "+ event['detail']['instance-id'] +" does not exist."
                return 'Failure'

            else:
                # All successful, let's move on.
                break



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


        # Finally we need to create entries in the Route53 zone for this new
        # EC2 instance. We take the ID we have and get the zone name as well.

        client_r53 = boto3.client('route53')

        try:
            cfg_r53_zone_name = client_r53.get_hosted_zone(Id=cfg_r53_zone_id)['HostedZone']['Name']
        except KeyError as e:
            # Catch misconfiguration by admin
            print "Hosted zone ID "+ cfg_r53_zone_id +" does not appear to exist."
            return 'Failure'

        print "Resolved zone ID "+ cfg_r53_zone_id +" as domain "+ cfg_r53_zone_name

        client_r53.change_resource_record_sets(
            HostedZoneId=cfg_r53_zone_id,
            ChangeBatch={
                'Changes': [
                    # Create a record for the label hostname we have created.
                    {
                        'Action': 'UPSERT',
                        'ResourceRecordSet': {
                            'Name': hostname + '.' + cfg_r53_zone_name,
                            'Type': 'A',
                            'TTL': 86400,
                            'ResourceRecords': [
                                {
                                    'Value': instance_details['PrivateIpAddress']
                                }
                            ]
                        }
                    },
                    # We create a record for the instance ID that servers can
                    # use to easily discover their hostname.
                    {
                        'Action': 'UPSERT',
                        'ResourceRecordSet': {
                            'Name': 'i-' + hostname_parts['instanceid'] + '.' + cfg_r53_zone_name,
                            'Type': 'CNAME',
                            'TTL': 86400,
                            'ResourceRecords': [
                                {
                                    'Value': hostname + '.' + cfg_r53_zone_name
                                }
                            ]
                        }
                    },
                ]
            }
        )


    except Exception as e:
        print 'An unexpected issue occured when interacting with the AWS APIs.'
        raise



    return 'Success'
