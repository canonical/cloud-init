"""Integration test for the ssh_import_id module.

This test specifies ssh keys to be imported by the ``ssh_import_id`` module
and then checks that if the ssh keys were successfully imported.

TODO:
* This test assumes that SSH keys will be imported into the /home/ubuntu; this
  will need modification to run on other OSes.

(This is ported from
``tests/cloud_tests/testcases/modules/ssh_import_id.yaml``.)"""

import pytest


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
    def test_ssh_import_id(self, client):
        ssh_output = client.read_from_file(
            "/home/ubuntu/.ssh/authorized_keys")

        assert '# ssh-import-id gh:powersj' in ssh_output
        assert '# ssh-import-id lp:smoser' in ssh_output
