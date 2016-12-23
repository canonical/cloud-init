# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import util as c_util

import json
import unittest


class CloudTestCase(unittest.TestCase):
    """
    base test class for verifiers
    """
    data = None
    conf = None
    _cloud_config = None

    @property
    def cloud_config(self):
        """
        get the cloud-config used by the test
        """
        if not self._cloud_config:
            self._cloud_config = c_util.load_yaml(self.conf)
        return self._cloud_config

    def get_config_entry(self, name):
        """
        get a config entry from cloud-config ensuring that it is present
        """
        if name not in self.cloud_config:
            raise AssertionError('Key "{}" not in cloud config'.format(name))
        return self.cloud_config[name]

    def get_data_file(self, name):
        """
        get data file failing test if it is not present
        """
        if name not in self.data:
            raise AssertionError('File "{}" missing from collect data'
                                 .format(name))
        return self.data[name]

    def get_instance_id(self):
        """
        get recorded instance id
        """
        return self.get_data_file('instance-id').strip()

    def get_status_data(self, data, version=None):
        """
        parse result.json and status.json like data files
        data: data to load
        version: cloud-init output version, defaults to 'v1'
        return_value: dict of data or None if missing
        """
        if not version:
            version = 'v1'
        data = json.loads(data)
        return data.get(version)

    def get_datasource(self):
        """
        get datasource name
        """
        data = self.get_status_data(self.get_data_file('result.json'))
        return data.get('datasource')

    def test_no_stages_errors(self):
        """
        ensure that there were no errors in any stage
        """
        status = self.get_status_data(self.get_data_file('status.json'))
        for stage in ('init', 'init-local', 'modules-config', 'modules-final'):
            self.assertIn(stage, status)
            self.assertEqual(len(status[stage]['errors']), 0,
                             'errors {} were encountered in stage {}'
                             .format(status[stage]['errors'], stage))
        result = self.get_status_data(self.get_data_file('result.json'))
        self.assertEqual(len(result['errors']), 0)

# vi: ts=4 expandtab
