# This file is part of cloud-init. See LICENSE file for license information.

"""Base EC2 instance."""
import os

import botocore

from ..instances import Instance
from tests.cloud_tests import LOG, util


class EC2Instance(Instance):
    """EC2 backed instance."""

    platform_name = "ec2"
    _ssh_client = None

    def __init__(self, platform, properties, config, features,
                 image_ami, user_data=None):
        """Set up instance.

        @param platform: platform object
        @param properties: dictionary of properties
        @param config: dictionary of configuration values
        @param features: dictionary of supported feature flags
        @param image_ami: AWS AMI ID for image to use
        @param user_data: test user-data to pass to instance
        """
        super(EC2Instance, self).__init__(
            platform, image_ami, properties, config, features)

        self.image_ami = image_ami
        self.instance = None
        self.user_data = user_data
        self.ssh_ip = None
        self.ssh_port = 22
        self.ssh_key_file = os.path.join(
            platform.config['data_dir'], platform.config['private_key'])
        self.ssh_pubkey_file = os.path.join(
            platform.config['data_dir'], platform.config['public_key'])

    def console_log(self):
        """Collect console log from instance.

        The console log is buffered and not always present, therefore
        may return empty string.
        """
        try:
            # OutputBytes comes from platform._decode_console_output_as_bytes
            response = self.instance.console_output()
            return response['OutputBytes']
        except KeyError:
            if 'Output' in response:
                msg = ("'OutputBytes' did not exist in console_output() but "
                       "'Output' did: %s..." % response['Output'][0:128])
                raise util.PlatformError('console_log', msg)
            return ('No Console Output [%s]' % self.instance).encode()

    def destroy(self):
        """Clean up instance."""
        if self.instance:
            LOG.debug('destroying instance %s', self.instance.id)
            self.instance.terminate()
            self.instance.wait_until_terminated()

        self._ssh_close()

        super(EC2Instance, self).destroy()

    def _execute(self, command, stdin=None, env=None):
        """Execute command on instance."""
        env_args = []
        if env:
            env_args = ['env'] + ["%s=%s" for k, v in env.items()]

        return self._ssh(['sudo'] + env_args + list(command), stdin=stdin)

    def start(self, wait=True, wait_for_cloud_init=False):
        """Start instance on EC2 with the platfrom's VPC."""
        if self.instance:
            if self.instance.state['Name'] == 'running':
                return

            LOG.debug('starting instance %s', self.instance.id)
            self.instance.start()
        else:
            LOG.debug('launching instance')

            args = {
                'ImageId': self.image_ami,
                'InstanceType': self.platform.instance_type,
                'KeyName': self.platform.key_name,
                'MaxCount': 1,
                'MinCount': 1,
                'SecurityGroupIds': [self.platform.security_group.id],
                'SubnetId': self.platform.subnet.id,
                'TagSpecifications': [{
                    'ResourceType': 'instance',
                    'Tags': [{
                        'Key': 'Name', 'Value': self.platform.tag
                    }]
                }],
            }

            if self.user_data:
                args['UserData'] = self.user_data

            try:
                instances = self.platform.ec2_resource.create_instances(**args)
            except botocore.exceptions.ClientError as error:
                error_msg = error.response['Error']['Message']
                raise util.PlatformError('start', error_msg)

            self.instance = instances[0]

        LOG.debug('instance id: %s', self.instance.id)
        if wait:
            self.instance.wait_until_running()
            self.instance.reload()
            self.ssh_ip = self.instance.public_ip_address
            self._wait_for_system(wait_for_cloud_init)

    def shutdown(self, wait=True):
        """Shutdown instance."""
        LOG.debug('stopping instance %s', self.instance.id)
        self.instance.stop()

        if wait:
            self.instance.wait_until_stopped()
            self.instance.reload()

# vi: ts=4 expandtab
