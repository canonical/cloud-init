from cloudinit.sources import DataSourceNoCloud

from mocker import MockerTestCase


class TestNoCloudDataSource(MockerTestCase):

    def setUp(self):
        super(TestNoCloudDataSource, self).setUp()

    def test_parse_cmdline_data_valid(self):
        parse = DataSourceNoCloud.parse_cmdline_data

        ds_id = "ds=nocloud"
        pairs = (
            ("root=/dev/sda1 %(ds_id)s", {}),
            ("%(ds_id)s; root=/dev/foo", {}),
            ("%(ds_id)s", {}),
            ("%(ds_id)s;", {}),
            ("%(ds_id)s;s=SEED", {'seedfrom': 'SEED'}),
            ("%(ds_id)s;seedfrom=SEED;local-hostname=xhost",
             {'seedfrom': 'SEED', 'local-hostname': 'xhost'}),
            ("%(ds_id)s;h=xhost",
             {'local-hostname': 'xhost'}),
            ("%(ds_id)s;h=xhost;i=IID",
             {'local-hostname': 'xhost', 'instance-id': 'IID'}),
        )

        for (fmt, expected) in pairs:
            fill = {}
            cmdline = fmt % {'ds_id': ds_id}
            ret = parse(ds_id=ds_id, fill=fill, cmdline=cmdline)
            self.assertEqual(expected, fill)
            self.assertTrue(ret)

    def test_parse_cmdline_data_none(self):
        parse = DataSourceNoCloud.parse_cmdline_data

        ds_id = "ds=foo"
        cmdlines = (
            "root=/dev/sda1 ro",
            "console=/dev/ttyS0 root=/dev/foo",
            "",
            "ds=foocloud",
            "ds=foo-net",
            "ds=nocloud;s=SEED",
        )

        for cmdline in cmdlines:
            fill = {}
            ret = parse(ds_id=ds_id, fill=fill, cmdline=cmdline)
            self.assertEqual(fill, {})
            self.assertFalse(ret)


# vi: ts=4 expandtab
