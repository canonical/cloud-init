# This file is part of cloud-init. See LICENSE file for license information.

from . import helpers

from cloudinit import ec2_utils as eu
from cloudinit import url_helper as uh

hp = helpers.import_httpretty()


class TestEc2Util(helpers.HttprettyTestCase):
    VERSION = 'latest'

    @hp.activate
    def test_userdata_fetch(self):
        hp.register_uri(hp.GET,
                        'http://169.254.169.254/%s/user-data' % (self.VERSION),
                        body='stuff',
                        status=200)
        userdata = eu.get_instance_userdata(self.VERSION)
        self.assertEqual('stuff', userdata.decode('utf-8'))

    @hp.activate
    def test_userdata_fetch_fail_not_found(self):
        hp.register_uri(hp.GET,
                        'http://169.254.169.254/%s/user-data' % (self.VERSION),
                        status=404)
        userdata = eu.get_instance_userdata(self.VERSION, retries=0)
        self.assertEqual('', userdata)

    @hp.activate
    def test_userdata_fetch_fail_server_dead(self):
        hp.register_uri(hp.GET,
                        'http://169.254.169.254/%s/user-data' % (self.VERSION),
                        status=500)
        userdata = eu.get_instance_userdata(self.VERSION, retries=0)
        self.assertEqual('', userdata)

    @hp.activate
    def test_userdata_fetch_fail_server_not_found(self):
        hp.register_uri(hp.GET,
                        'http://169.254.169.254/%s/user-data' % (self.VERSION),
                        status=404)
        userdata = eu.get_instance_userdata(self.VERSION)
        self.assertEqual('', userdata)

    @hp.activate
    def test_metadata_fetch_no_keys(self):
        base_url = 'http://169.254.169.254/%s/meta-data/' % (self.VERSION)
        hp.register_uri(hp.GET, base_url, status=200,
                        body="\n".join(['hostname',
                                        'instance-id',
                                        'ami-launch-index']))
        hp.register_uri(hp.GET, uh.combine_url(base_url, 'hostname'),
                        status=200, body='ec2.fake.host.name.com')
        hp.register_uri(hp.GET, uh.combine_url(base_url, 'instance-id'),
                        status=200, body='123')
        hp.register_uri(hp.GET, uh.combine_url(base_url, 'ami-launch-index'),
                        status=200, body='1')
        md = eu.get_instance_metadata(self.VERSION, retries=0)
        self.assertEqual(md['hostname'], 'ec2.fake.host.name.com')
        self.assertEqual(md['instance-id'], '123')
        self.assertEqual(md['ami-launch-index'], '1')

    @hp.activate
    def test_metadata_fetch_key(self):
        base_url = 'http://169.254.169.254/%s/meta-data/' % (self.VERSION)
        hp.register_uri(hp.GET, base_url, status=200,
                        body="\n".join(['hostname',
                                        'instance-id',
                                        'public-keys/']))
        hp.register_uri(hp.GET, uh.combine_url(base_url, 'hostname'),
                        status=200, body='ec2.fake.host.name.com')
        hp.register_uri(hp.GET, uh.combine_url(base_url, 'instance-id'),
                        status=200, body='123')
        hp.register_uri(hp.GET, uh.combine_url(base_url, 'public-keys/'),
                        status=200, body='0=my-public-key')
        hp.register_uri(hp.GET,
                        uh.combine_url(base_url, 'public-keys/0/openssh-key'),
                        status=200, body='ssh-rsa AAAA.....wZEf my-public-key')
        md = eu.get_instance_metadata(self.VERSION, retries=0, timeout=0.1)
        self.assertEqual(md['hostname'], 'ec2.fake.host.name.com')
        self.assertEqual(md['instance-id'], '123')
        self.assertEqual(1, len(md['public-keys']))

    @hp.activate
    def test_metadata_fetch_with_2_keys(self):
        base_url = 'http://169.254.169.254/%s/meta-data/' % (self.VERSION)
        hp.register_uri(hp.GET, base_url, status=200,
                        body="\n".join(['hostname',
                                        'instance-id',
                                        'public-keys/']))
        hp.register_uri(hp.GET, uh.combine_url(base_url, 'hostname'),
                        status=200, body='ec2.fake.host.name.com')
        hp.register_uri(hp.GET, uh.combine_url(base_url, 'instance-id'),
                        status=200, body='123')
        hp.register_uri(hp.GET, uh.combine_url(base_url, 'public-keys/'),
                        status=200,
                        body="\n".join(['0=my-public-key', '1=my-other-key']))
        hp.register_uri(hp.GET,
                        uh.combine_url(base_url, 'public-keys/0/openssh-key'),
                        status=200, body='ssh-rsa AAAA.....wZEf my-public-key')
        hp.register_uri(hp.GET,
                        uh.combine_url(base_url, 'public-keys/1/openssh-key'),
                        status=200, body='ssh-rsa AAAA.....wZEf my-other-key')
        md = eu.get_instance_metadata(self.VERSION, retries=0, timeout=0.1)
        self.assertEqual(md['hostname'], 'ec2.fake.host.name.com')
        self.assertEqual(md['instance-id'], '123')
        self.assertEqual(2, len(md['public-keys']))

    @hp.activate
    def test_metadata_fetch_bdm(self):
        base_url = 'http://169.254.169.254/%s/meta-data/' % (self.VERSION)
        hp.register_uri(hp.GET, base_url, status=200,
                        body="\n".join(['hostname',
                                        'instance-id',
                                        'block-device-mapping/']))
        hp.register_uri(hp.GET, uh.combine_url(base_url, 'hostname'),
                        status=200, body='ec2.fake.host.name.com')
        hp.register_uri(hp.GET, uh.combine_url(base_url, 'instance-id'),
                        status=200, body='123')
        hp.register_uri(hp.GET,
                        uh.combine_url(base_url, 'block-device-mapping/'),
                        status=200,
                        body="\n".join(['ami', 'ephemeral0']))
        hp.register_uri(hp.GET,
                        uh.combine_url(base_url, 'block-device-mapping/ami'),
                        status=200,
                        body="sdb")
        hp.register_uri(hp.GET,
                        uh.combine_url(base_url,
                                       'block-device-mapping/ephemeral0'),
                        status=200,
                        body="sdc")
        md = eu.get_instance_metadata(self.VERSION, retries=0, timeout=0.1)
        self.assertEqual(md['hostname'], 'ec2.fake.host.name.com')
        self.assertEqual(md['instance-id'], '123')
        bdm = md['block-device-mapping']
        self.assertEqual(2, len(bdm))
        self.assertEqual(bdm['ami'], 'sdb')
        self.assertEqual(bdm['ephemeral0'], 'sdc')

# vi: ts=4 expandtab
