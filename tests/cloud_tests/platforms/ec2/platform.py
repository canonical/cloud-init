# This file is part of cloud-init. See LICENSE file for license information.

"""Base EC2 platform."""
from datetime import datetime
import os

import boto3
import botocore
from botocore import session, handlers
import base64

from ..platforms import Platform
from .image import EC2Image
from .instance import EC2Instance
from tests.cloud_tests import LOG


class EC2Platform(Platform):
    """EC2 test platform."""

    platform_name = 'ec2'
    ipv4_cidr = '192.168.1.0/20'

    def __init__(self, config):
        """Set up platform."""
        super(EC2Platform, self).__init__(config)
        # Used for unique VPC, SSH key, and custom AMI generation naming
        self.tag = '%s-%s' % (
            config['tag'], datetime.now().strftime('%Y%m%d%H%M%S'))
        self.instance_type = config['instance-type']

        try:
            b3session = get_session()
            self.ec2_client = b3session.client('ec2')
            self.ec2_resource = b3session.resource('ec2')
            self.ec2_region = b3session.region_name
            self.key_name = self._upload_public_key(config)
        except botocore.exceptions.NoRegionError:
            raise RuntimeError(
                'Please configure default region in $HOME/.aws/config')
        except botocore.exceptions.NoCredentialsError:
            raise RuntimeError(
                'Please configure ec2 credentials in $HOME/.aws/credentials')

        self.vpc = self._create_vpc()
        self.internet_gateway = self._create_internet_gateway()
        self.subnet = self._create_subnet()
        self.routing_table = self._create_routing_table()
        self.security_group = self._create_security_group()

    def create_instance(self, properties, config, features,
                        image_ami, user_data=None):
        """Create an instance

        @param src_img_path: image path to launch from
        @param properties: image properties
        @param config: image configuration
        @param features: image features
        @param image_ami: string of image ami ID
        @param user_data: test user-data to pass to instance
        @return_value: cloud_tests.instances instance
        """
        return EC2Instance(self, properties, config, features,
                           image_ami, user_data)

    def destroy(self):
        """Delete SSH keys, terminate all instances, and delete VPC."""
        for instance in self.vpc.instances.all():
            LOG.debug('waiting for instance %s termination', instance.id)
            instance.terminate()
            instance.wait_until_terminated()

        if self.key_name:
            LOG.debug('deleting SSH key %s', self.key_name)
            self.ec2_client.delete_key_pair(KeyName=self.key_name)

        if self.security_group:
            LOG.debug('deleting security group %s', self.security_group.id)
            self.security_group.delete()

        if self.subnet:
            LOG.debug('deleting subnet %s', self.subnet.id)
            self.subnet.delete()

        if self.routing_table:
            LOG.debug('deleting routing table %s', self.routing_table.id)
            self.routing_table.delete()

        if self.internet_gateway:
            LOG.debug('deleting internet gateway %s', self.internet_gateway.id)
            self.internet_gateway.detach_from_vpc(VpcId=self.vpc.id)
            self.internet_gateway.delete()

        if self.vpc:
            LOG.debug('deleting vpc %s', self.vpc.id)
            self.vpc.delete()

    def get_image(self, img_conf):
        """Get image using specified image configuration.

        Hard coded for 'amd64' based images.

        @param img_conf: configuration for image
        @return_value: cloud_tests.images instance
        """
        if img_conf['root-store'] == 'ebs':
            root_store = 'ssd'
        elif img_conf['root-store'] == 'instance-store':
            root_store = 'instance'
        else:
            raise RuntimeError('Unknown root-store type: %s' %
                               (img_conf['root-store']))

        filters = [
            'arch=%s' % 'amd64',
            'endpoint=https://ec2.%s.amazonaws.com' % self.ec2_region,
            'region=%s' % self.ec2_region,
            'release=%s' % img_conf['release'],
            'root_store=%s' % root_store,
            'virt=hvm',
        ]

        LOG.debug('finding image using streams')
        image = self._query_streams(img_conf, filters)

        try:
            image_ami = image['id']
        except KeyError:
            raise RuntimeError('No images found for %s!' % img_conf['release'])

        LOG.debug('found image: %s', image_ami)
        image = EC2Image(self, img_conf, image_ami)
        return image

    def _create_internet_gateway(self):
        """Create Internet Gateway and assign to VPC."""
        LOG.debug('creating internet gateway')
        internet_gateway = self.ec2_resource.create_internet_gateway()
        internet_gateway.attach_to_vpc(VpcId=self.vpc.id)
        self._tag_resource(internet_gateway)

        return internet_gateway

    def _create_routing_table(self):
        """Update default routing table with internet gateway.

        This sets up internet access between the VPC via the internet gateway
        by configuring routing tables for IPv4 and IPv6.
        """
        LOG.debug('creating routing table')
        route_table = self.vpc.create_route_table()
        route_table.create_route(DestinationCidrBlock='0.0.0.0/0',
                                 GatewayId=self.internet_gateway.id)
        route_table.create_route(DestinationIpv6CidrBlock='::/0',
                                 GatewayId=self.internet_gateway.id)
        route_table.associate_with_subnet(SubnetId=self.subnet.id)
        self._tag_resource(route_table)

        return route_table

    def _create_security_group(self):
        """Enables ingress to default VPC security group."""
        LOG.debug('creating security group')
        security_group = self.vpc.create_security_group(
            GroupName=self.tag, Description='integration test security group')
        security_group.authorize_ingress(
            IpProtocol='-1', FromPort=-1, ToPort=-1, CidrIp='0.0.0.0/0')
        self._tag_resource(security_group)

        return security_group

    def _create_subnet(self):
        """Generate IPv4 and IPv6 subnets for use."""
        ipv6_cidr = self.vpc.ipv6_cidr_block_association_set[0][
            'Ipv6CidrBlock'][:-2] + '64'

        LOG.debug('creating subnet with following ranges:')
        LOG.debug('ipv4: %s', self.ipv4_cidr)
        LOG.debug('ipv6: %s', ipv6_cidr)
        subnet = self.vpc.create_subnet(CidrBlock=self.ipv4_cidr,
                                        Ipv6CidrBlock=ipv6_cidr)
        modify_subnet = subnet.meta.client.modify_subnet_attribute
        modify_subnet(SubnetId=subnet.id,
                      MapPublicIpOnLaunch={'Value': True})
        self._tag_resource(subnet)

        return subnet

    def _create_vpc(self):
        """Setup AWS EC2 VPC or return existing VPC."""
        LOG.debug('creating new vpc')
        try:
            vpc = self.ec2_resource.create_vpc(
                CidrBlock=self.ipv4_cidr,
                AmazonProvidedIpv6CidrBlock=True)
        except botocore.exceptions.ClientError as e:
            raise RuntimeError(e)

        vpc.wait_until_available()
        self._tag_resource(vpc)

        return vpc

    def _tag_resource(self, resource):
        """Tag a resource with the specified tag.

        This makes finding and deleting resources specific to this testing
        much easier to find.

        @param resource: resource to tag
        """
        tag = {
            'Key': 'Name',
            'Value': self.tag
        }
        resource.create_tags(Tags=[tag])

    def _upload_public_key(self, config):
        """Generate random name and upload SSH key with that name.

        @param config: platform config
        @return: string of ssh key name
        """
        key_file = os.path.join(config['data_dir'], config['public_key'])
        with open(key_file, 'r') as file:
            public_key = file.read().strip('\n')

        LOG.debug('uploading SSH key %s', self.tag)
        self.ec2_client.import_key_pair(KeyName=self.tag,
                                        PublicKeyMaterial=public_key)

        return self.tag


def _decode_console_output_as_bytes(parsed, **kwargs):
    """Provide console output as bytes in OutputBytes.

       For this to be useful, the session has to have had the
       decode_console_output handler unregistered already.

       https://github.com/boto/botocore/issues/1351 ."""
    if 'Output' not in parsed:
        return
    orig = parsed['Output']
    handlers.decode_console_output(parsed, **kwargs)
    parsed['OutputBytes'] = base64.b64decode(orig)


def get_session():
    mysess = session.get_session()
    mysess.unregister('after-call.ec2.GetConsoleOutput',
                      handlers.decode_console_output)
    mysess.register('after-call.ec2.GetConsoleOutput',
                    _decode_console_output_as_bytes)
    return boto3.Session(botocore_session=mysess)


# vi: ts=4 expandtab
