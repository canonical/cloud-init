# This file is part of cloud-init. See LICENSE file for license information.
from logging import DEBUG, WARNING
from pathlib import Path

import pytest

from cloudinit.config.cc_final_message import handle
from tests.unittests.util import get_cloud


class TestHandle:
    # TODO: Expand these tests to cover full functionality; currently they only
    # cover the logic around how the boot-finished file is written (and not its
    # contents).

    @pytest.mark.parametrize(
        "instance_dir_exists,file_is_written,expected_log_substring",
        [
            (True, True, None),
            (False, False, "Failed to write boot finished file "),
        ],
    )
    def test_boot_finished_written(
        self,
        instance_dir_exists,
        file_is_written,
        expected_log_substring,
        caplog,
        paths,
        tmpdir,
    ):
        instance_dir = Path(paths.get_ipath_cur())
        if instance_dir_exists:
            instance_dir.mkdir()
        boot_finished = instance_dir / "boot-finished"

        m_cloud = get_cloud(paths=paths)
        handle(None, {}, m_cloud, [])

        # We should not change the status of the instance directory
        assert instance_dir_exists == instance_dir.exists()
        assert file_is_written == boot_finished.exists()

        if expected_log_substring:
            assert expected_log_substring in caplog.text

    @pytest.mark.parametrize(
        "dsname,datasource_list,expected_log,log_level",
        [
            ("None", ["None"], "Used fallback datasource", DEBUG),
            ("None", ["LXD", "None"], "Used fallback datasource", WARNING),
            ("LXD", ["LXD", "None"], None, DEBUG),
        ],
    )
    def test_only_warn_when_datasourcenone_is_fallback_in_datasource_list(
        self,
        dsname,
        datasource_list,
        expected_log,
        log_level,
        caplog,
        paths,
    ):
        """Only warn when None is a fallback in multi-item datasource_list.

        It is not a warning when datasource_list: [ None ] is configured.
        """
        m_cloud = get_cloud(paths=paths)
        m_cloud.datasource.dsname = dsname
        Path(paths.get_ipath_cur()).mkdir()
        with caplog.at_level(log_level):
            handle(None, {}, m_cloud, [])

        # We should not change the status of the instance directory
        if expected_log:
            assert expected_log in caplog.text
        else:
            assert "Used fallback datasource" not in caplog.text
