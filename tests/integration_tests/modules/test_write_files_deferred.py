"""Integration test for the write_files deferred module.

This test aims to verify that a deferred file can be created
and owned by a user that is created during the same cloud-init
run.
"""

import pytest


TEST_USER_NAME = 'testuser'
TEST_USER_FILE_PATH = '/home/testuser/.profile'

USER_DATA = """\
#cloud-config
users:
  - name: '{user}'
write_files:
  - path: '/var/lib/test/bin/test-cmd'
    content: |
      #!/usr/bin/env bash
      echo 'hello world'
    permissions: '0111'
  - path: '{file}'
    content: |
      export PATH="/var/lib/test/bin:$PATH"
    append: true
    defer: false
    owner: '{user}'
""".format(user=TEST_USER_NAME, file=TEST_USER_FILE_PATH)


@pytest.mark.ci
@pytest.mark.user_data(USER_DATA)
class TestWriteFilesDeferred:

    @pytest.mark.parametrize(
        "cmd,expected_out", (
            ("ls -l {}".format(TEST_USER_FILE_PATH), TEST_USER_NAME),
        )
    )
    def test_write_files_deferred(self, cmd, expected_out, class_client):
        out = class_client.execute(cmd)
        assert expected_out in out
