# This file is part of cloud-init. See LICENSE file for license information.
from unittest import mock

import pytest

from cloudinit.config.cc_final_message import handle


class TestHandle:
    # TODO: Expand these tests to cover full functionality; currently they only
    # cover the logic around how the boot-finished file is written (and not its
    # contents).

    @pytest.mark.parametrize(
        "instance_dir_exists,file_is_written", [(True, True), (False, False)]
    )
    def test_boot_finished_written(
        self, instance_dir_exists, file_is_written, tmpdir
    ):
        instance_dir = tmpdir.join("var/lib/cloud/instance")
        if instance_dir_exists:
            instance_dir.ensure_dir()
        boot_finished = instance_dir.join("boot-finished")

        m_cloud = mock.Mock(paths=mock.Mock(boot_finished=boot_finished))

        handle(None, {}, m_cloud, mock.Mock(), [])

        # We should not change the status of the instance directory
        assert instance_dir_exists == instance_dir.exists()
        assert file_is_written == boot_finished.exists()
