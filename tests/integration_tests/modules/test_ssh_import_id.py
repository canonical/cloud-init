"""Integration test for the ssh_import_id module.

This test specifies ssh keys to be imported by the ``ssh_import_id`` module
and then checks that if the ssh keys were successfully imported.

TODO:
* This test assumes that SSH keys will be imported into the /home/ubuntu; this
  will need modification to run on other OSes.

(This is ported from
``tests/cloud_tests/testcases/modules/ssh_import_id.yaml``.)"""

import pytest

from tests.integration_tests.util import retry

USER_DATA = """\
#cloud-config
ssh_import_id:
  - gh:powersj
  - lp:smoser
"""


@pytest.mark.ci
@pytest.mark.ubuntu
class TestSshImportId:

    @pytest.mark.user_data(USER_DATA)
    # Retry is needed here because ssh import id is one of the last modules
    # run, and it fires off a web request, then continues with the rest of
    # cloud-init. It is possible cloud-init's status is "done" before the
    # id's have been fully imported.
    @retry(tries=30, delay=1)
    def test_ssh_import_id(self, client):
        ssh_output = client.read_from_file(
            "/home/ubuntu/.ssh/authorized_keys")

        assert '# ssh-import-id gh:powersj' in ssh_output
        assert '# ssh-import-id lp:smoser' in ssh_output
