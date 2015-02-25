# Copyright (C) 2015 Canonical Ltd.
# Copyright 2015 Cloudbase Solutions Srl
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import unittest

try:
    import unittest.mock as mock
except ImportError:
    import mock

from cloudinit.osys import base


class TestOSUtils(unittest.TestCase):

    @mock.patch('importlib.import_module')
    @mock.patch('platform.linux_distribution')
    @mock.patch('platform.system')
    def _test_getosutils(self, mock_system,
                         mock_linux_distribution, mock_import_module,
                         linux=False):
        if linux:
            os_name = 'Linux'            
        else:
            os_name = 'Windows'

        mock_system.return_value = os_name
        mock_linux_distribution.return_value = (os_name, None, None)
        module = base.get_osutils()

        mock_import_module.assert_called_once_with(
            "cloudinit.osys.{0}.base".format(os_name.lower()))
        self.assertEqual(mock_import_module.return_value.OSUtils,
                         module)

    def test_getosutils(self):
        self._test_getosutils(linux=True)
        self._test_getosutils(linux=False)
