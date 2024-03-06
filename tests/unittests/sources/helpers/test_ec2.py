# This file is part of cloud-init. See LICENSE file for license information.

import responses

from cloudinit import url_helper as uh
from cloudinit.sources.helpers import ec2
from tests.unittests import helpers


class TestEc2Util(helpers.ResponsesTestCase):
    VERSION = "latest"

    def test_userdata_fetch(self):
        self.responses.add(
            responses.GET,
            "http://169.254.169.254/%s/user-data" % (self.VERSION),
            body="stuff",
            status=200,
        )
        userdata = ec2.get_instance_userdata(self.VERSION)
        self.assertEqual("stuff", userdata.decode("utf-8"))

    def test_userdata_fetch_fail_not_found(self):
        self.responses.add(
            responses.GET,
            "http://169.254.169.254/%s/user-data" % (self.VERSION),
            status=404,
        )
        userdata = ec2.get_instance_userdata(self.VERSION, retries=0)
        self.assertEqual(b"", userdata)

    def test_userdata_fetch_fail_server_dead(self):
        self.responses.add(
            responses.GET,
            "http://169.254.169.254/%s/user-data" % (self.VERSION),
            status=500,
        )
        userdata = ec2.get_instance_userdata(self.VERSION, retries=0)
        self.assertEqual(b"", userdata)

    def test_userdata_fetch_fail_server_not_found(self):
        self.responses.add(
            responses.GET,
            "http://169.254.169.254/%s/user-data" % (self.VERSION),
            status=404,
        )
        userdata = ec2.get_instance_userdata(self.VERSION)
        self.assertEqual(b"", userdata)

    def test_metadata_fetch_no_keys(self):
        base_url = "http://169.254.169.254/%s/meta-data/" % (self.VERSION)
        self.responses.add(
            responses.GET,
            base_url,
            status=200,
            body="\n".join(["hostname", "instance-id", "ami-launch-index"]),
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "hostname"),
            status=200,
            body="ec2.fake.host.name.com",
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "instance-id"),
            status=200,
            body="123",
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "ami-launch-index"),
            status=200,
            body="1",
        )
        md = ec2.get_instance_metadata(self.VERSION, retries=0)
        self.assertEqual(md["hostname"], "ec2.fake.host.name.com")
        self.assertEqual(md["instance-id"], "123")
        self.assertEqual(md["ami-launch-index"], "1")

    def test_metadata_fetch_key(self):
        base_url = "http://169.254.169.254/%s/meta-data/" % (self.VERSION)
        self.responses.add(
            responses.GET,
            base_url,
            status=200,
            body="\n".join(["hostname", "instance-id", "public-keys/"]),
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "hostname"),
            status=200,
            body="ec2.fake.host.name.com",
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "instance-id"),
            status=200,
            body="123",
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "public-keys/"),
            status=200,
            body="0=my-public-key",
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "public-keys/0/openssh-key"),
            status=200,
            body="ssh-rsa AAAA.....wZEf my-public-key",
        )
        md = ec2.get_instance_metadata(self.VERSION, retries=0, timeout=0.1)
        self.assertEqual(md["hostname"], "ec2.fake.host.name.com")
        self.assertEqual(md["instance-id"], "123")
        self.assertEqual(1, len(md["public-keys"]))

    def test_metadata_fetch_with_2_keys(self):
        base_url = "http://169.254.169.254/%s/meta-data/" % (self.VERSION)
        self.responses.add(
            responses.GET,
            base_url,
            status=200,
            body="\n".join(["hostname", "instance-id", "public-keys/"]),
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "hostname"),
            status=200,
            body="ec2.fake.host.name.com",
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "instance-id"),
            status=200,
            body="123",
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "public-keys/"),
            status=200,
            body="\n".join(["0=my-public-key", "1=my-other-key"]),
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "public-keys/0/openssh-key"),
            status=200,
            body="ssh-rsa AAAA.....wZEf my-public-key",
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "public-keys/1/openssh-key"),
            status=200,
            body="ssh-rsa AAAA.....wZEf my-other-key",
        )
        md = ec2.get_instance_metadata(self.VERSION, retries=0, timeout=0.1)
        self.assertEqual(md["hostname"], "ec2.fake.host.name.com")
        self.assertEqual(md["instance-id"], "123")
        self.assertEqual(2, len(md["public-keys"]))

    def test_metadata_fetch_bdm(self):
        base_url = "http://169.254.169.254/%s/meta-data/" % (self.VERSION)
        self.responses.add(
            responses.GET,
            base_url,
            status=200,
            body="\n".join(
                ["hostname", "instance-id", "block-device-mapping/"]
            ),
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "hostname"),
            status=200,
            body="ec2.fake.host.name.com",
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "instance-id"),
            status=200,
            body="123",
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "block-device-mapping/"),
            status=200,
            body="\n".join(["ami", "ephemeral0"]),
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "block-device-mapping/ami"),
            status=200,
            body="sdb",
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "block-device-mapping/ephemeral0"),
            status=200,
            body="sdc",
        )
        md = ec2.get_instance_metadata(self.VERSION, retries=0, timeout=0.1)
        self.assertEqual(md["hostname"], "ec2.fake.host.name.com")
        self.assertEqual(md["instance-id"], "123")
        bdm = md["block-device-mapping"]
        self.assertEqual(2, len(bdm))
        self.assertEqual(bdm["ami"], "sdb")
        self.assertEqual(bdm["ephemeral0"], "sdc")

    def test_metadata_no_security_credentials(self):
        base_url = "http://169.254.169.254/%s/meta-data/" % (self.VERSION)
        self.responses.add(
            responses.GET,
            base_url,
            status=200,
            body="\n".join(["instance-id", "iam/"]),
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "instance-id"),
            status=200,
            body="i-0123451689abcdef0",
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "iam/"),
            status=200,
            body="\n".join(["info/", "security-credentials/"]),
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "iam/info/"),
            status=200,
            body="LastUpdated",
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "iam/info/LastUpdated"),
            status=200,
            body="2016-10-27T17:29:39Z",
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "iam/security-credentials/"),
            status=200,
            body="ReadOnly/",
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "iam/security-credentials/ReadOnly/"),
            status=200,
            body="\n".join(["LastUpdated", "Expiration"]),
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(
                base_url, "iam/security-credentials/ReadOnly/LastUpdated"
            ),
            status=200,
            body="2016-10-27T17:28:17Z",
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(
                base_url, "iam/security-credentials/ReadOnly/Expiration"
            ),
            status=200,
            body="2016-10-28T00:00:34Z",
        )
        md = ec2.get_instance_metadata(self.VERSION, retries=0, timeout=0.1)
        self.assertEqual(md["instance-id"], "i-0123451689abcdef0")
        iam = md["iam"]
        self.assertEqual(1, len(iam))
        self.assertEqual(iam["info"]["LastUpdated"], "2016-10-27T17:29:39Z")
        self.assertNotIn("security-credentials", iam)

    def test_metadata_children_with_invalid_character(self):
        def _skip_tags(exception):
            if isinstance(exception, uh.UrlError) and exception.code == 404:
                if "meta-data/tags/" in exception.url:
                    print(exception.url)
                    return True
            return False

        base_url = "http://169.254.169.254/%s/meta-data/" % (self.VERSION)
        self.responses.add(
            responses.GET,
            base_url,
            status=200,
            body="\n".join(["tags/", "ami-launch-index"]),
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "tags/"),
            status=200,
            body="\n".join(["test/invalid", "valid"]),
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "tags/valid"),
            status=200,
            body="OK",
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "tags/test/invalid"),
            status=404,
        )
        self.responses.add(
            responses.GET,
            uh.combine_url(base_url, "ami-launch-index"),
            status=200,
            body="1",
        )
        md = ec2.get_instance_metadata(
            self.VERSION,
            retries=0,
            timeout=0.1,
            retrieval_exception_ignore_cb=_skip_tags,
        )
        self.assertEqual(md["tags"]["valid"], "OK")
        self.assertEqual(md["tags"]["test/invalid"], "(skipped)")
        self.assertEqual(md["ami-launch-index"], "1")
        md = ec2.get_instance_metadata(self.VERSION, retries=0, timeout=0.1)
        self.assertEqual(len(md), 0)
