# This file is part of cloud-init. See LICENSE file for license information.
from logging import DEBUG, WARNING
from pathlib import Path

import pytest

from cloudinit.config.cc_final_message import handle
from tests.unittests.util import get_cloud


class TestHandle:
    def test_final_message_logged_without_boot_finished_write(
        self,
        mocker,
        paths,
    ):
        instance_dir = Path(paths.get_ipath_cur())
        instance_dir.mkdir()
        boot_finished = instance_dir / "boot-finished"
        m_multi_log = mocker.patch(
            "cloudinit.config.cc_final_message.log_util.multi_log"
        )

        m_cloud = get_cloud(paths=paths)
        handle(None, {}, m_cloud, [])

        # We should not change the status of the instance directory
        assert instance_dir.exists()
        assert not boot_finished.exists()
        assert "Cloud-init v." in m_multi_log.call_args[0][0]

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
