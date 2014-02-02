import re
import json

from StringIO import StringIO

from urlparse import urlparse

from tests.unittests import helpers

from cloudinit.sources import DataSourceOpenStack as ds
from cloudinit.sources.helpers import openstack
from cloudinit import util

import httpretty as hp

BASE_URL = "http://169.254.169.254"
PUBKEY = u'ssh-rsa AAAAB3NzaC1....sIkJhq8wdX+4I3A4cYbYP ubuntu@server-460\n'
EC2_META = {
    'ami-id': 'ami-00000001',
    'ami-launch-index': 0,
    'ami-manifest-path': 'FIXME',
    'hostname': 'sm-foo-test.novalocal',
    'instance-action': 'none',
    'instance-id': 'i-00000001',
    'instance-type': 'm1.tiny',
    'local-hostname': 'sm-foo-test.novalocal',
    'local-ipv4': '0.0.0.0',
    'public-hostname': 'sm-foo-test.novalocal',
    'public-ipv4': '0.0.0.1',
    'reservation-id': 'r-iru5qm4m',
}
USER_DATA = '#!/bin/sh\necho This is user data\n'
VENDOR_DATA = {
    'magic': '',
}
OSTACK_META = {
    'availability_zone': 'nova',
    'files': [{'content_path': '/content/0000', 'path': '/etc/foo.cfg'},
              {'content_path': '/content/0001', 'path': '/etc/bar/bar.cfg'}],
    'hostname': 'sm-foo-test.novalocal',
    'meta': {'dsmode': 'local', 'my-meta': 'my-value'},
    'name': 'sm-foo-test',
    'public_keys': {'mykey': PUBKEY},
    'uuid': 'b0fa911b-69d4-4476-bbe2-1c92bff6535c',
}
CONTENT_0 = 'This is contents of /etc/foo.cfg\n'
CONTENT_1 = '# this is /etc/bar/bar.cfg\n'
OS_FILES = {
    'openstack/2012-08-10/meta_data.json': json.dumps(OSTACK_META),
    'openstack/2012-08-10/user_data': USER_DATA,
    'openstack/content/0000': CONTENT_0,
    'openstack/content/0001': CONTENT_1,
    'openstack/latest/meta_data.json': json.dumps(OSTACK_META),
    'openstack/latest/user_data': USER_DATA,
    'openstack/latest/vendor_data.json': json.dumps(VENDOR_DATA),
}
EC2_FILES = {
    'latest/user-data': USER_DATA,
}


def _register_uris(version):

    def match_ec2_url(uri, headers):
        path = uri.path.lstrip("/")
        if path in EC2_FILES:
            return (200, headers, EC2_FILES.get(path))
        if path == 'latest/meta-data':
            buf = StringIO()
            for (k, v) in EC2_META.items():
                if isinstance(v, (list, tuple)):
                    buf.write("%s/" % (k))
                else:
                    buf.write("%s" % (k))
                buf.write("\n")
            return (200, headers, buf.getvalue())
        if path.startswith('latest/meta-data'):
            value = None
            pieces = path.split("/")
            if path.endswith("/"):
                pieces = pieces[2:-1]
                value = util.get_cfg_by_path(EC2_META, pieces)
            else:
                pieces = pieces[2:]
                value = util.get_cfg_by_path(EC2_META, pieces)
            if value is not None:
                return (200, headers, str(value))
        return (404, headers, '')

    def get_request_callback(method, uri, headers):
        uri = urlparse(uri)
        path = uri.path.lstrip("/")
        if path in OS_FILES:
            return (200, headers, OS_FILES.get(path))
        return match_ec2_url(uri, headers)

    def head_request_callback(method, uri, headers):
        uri = urlparse(uri)
        path = uri.path.lstrip("/")
        for key in OS_FILES.keys():
            if key.startswith(path):
                return (200, headers, '')
        return (404, headers, '')

    hp.register_uri(hp.GET, re.compile(r'http://169.254.169.254/.*'),
                    body=get_request_callback)

    hp.register_uri(hp.HEAD, re.compile(r'http://169.254.169.254/.*'),
                    body=head_request_callback)


class TestOpenStackDataSource(helpers.TestCase):
    VERSION = 'latest'

    @hp.activate
    def test_fetch(self):
        _register_uris(self.VERSION)
        f = ds.read_metadata_service(BASE_URL, version=self.VERSION)
        self.assertEquals(VENDOR_DATA, f.get('vendordata'))
        self.assertEquals(CONTENT_0, f['files']['/etc/foo.cfg'])
        self.assertEquals(CONTENT_1, f['files']['/etc/bar/bar.cfg'])
        self.assertEquals(USER_DATA, f.get('userdata'))
