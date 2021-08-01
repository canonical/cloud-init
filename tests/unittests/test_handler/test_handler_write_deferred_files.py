# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config.cc_write_deferred_files import (
    handle, extract_deferred_files)
from .test_handler_write_files import (VALID_SCHEMA, INVALID_SCHEMA)
from cloudinit import log as logging
from cloudinit import util

from cloudinit.tests.helpers import (
    CiTestCase, FilesystemMockingTestCase, mock, skipUnlessJsonSchema)

LOG = logging.getLogger(__name__)

YAML_TEXT = """
users:
  - name: 'bar'
    files:
      - path: '/home/bar/my-file.txt'
        content: |
          hi mom line 1
          hi mom line 2
"""


@skipUnlessJsonSchema()
@mock.patch('cloudinit.config.cc_write_deferred_files.write_files')
class TestWriteDeferredFilesSchema(CiTestCase):

    with_logs = True

    def test_schema_validation_warns_missing_path(self, m_write_deferred_files):
        """The only required file item property is 'path'."""

        valid_config =  {
            'users': [
                {'name': 'jeff',
                 'files': [
                    *VALID_SCHEMA.get('write_files'),
                    {'content': 'foo', 'path': '/bar'}
                ]}
            ]
        }

        invalid_config = {  # Dropped required path key
            'users': [
                {'name': 'jeff',
                 'files': INVALID_SCHEMA.get('write_files')}
            ]
        }

        cc = self.tmp_cloud('ubuntu')
        handle('cc_write_deferred_files', valid_config, cc, LOG, [])
        self.assertNotIn('Invalid config:', self.logs.getvalue())
        handle('cc_write_deferred_files', invalid_config, cc, LOG, [])
        self.assertIn('Invalid config:', self.logs.getvalue())
        self.assertIn("'path' is a required property", self.logs.getvalue())


class TestWriteDeferredFiles(FilesystemMockingTestCase):

    with_logs = True

    def test_extracting_file_list_and_default_values(self):
        cfg = util.load_yaml(YAML_TEXT)
        cloud = self.tmp_cloud('ubuntu')
        file_list = extract_deferred_files(cfg, cloud)
        self.assertEqual(len(file_list), 1)
        self.assertEqual(file_list[0].get('owner'), 'bar:bar')
        self.assertEqual(file_list[0].get('permissions'), '0600')


# vi: ts=4 expandtab
