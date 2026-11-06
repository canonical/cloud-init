# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for the cloud-init schema command line handling."""

import logging
from argparse import Namespace
from errno import EACCES
from unittest import mock

import pytest

from cloudinit.cmd import schema
from cloudinit.sources import DataSourceNotFoundException

M_PATH = "cloudinit.cmd.schema."


@mock.patch(M_PATH + "read_cfg_paths")
class TestGetPaths:
    def test_config_file_does_not_load_datasource(self, m_read_cfg_paths):
        args = Namespace(config_file="user-data", system=False)
        assert m_read_cfg_paths.return_value == schema.get_paths(args)
        assert [mock.call()] == m_read_cfg_paths.call_args_list

    def test_system_loads_cached_datasource(self, m_read_cfg_paths):
        args = Namespace(config_file=None, system=True)
        assert m_read_cfg_paths.return_value == schema.get_paths(args)
        assert [
            mock.call(fetch_existing_datasource="trust")
        ] == m_read_cfg_paths.call_args_list

    @pytest.mark.parametrize(
        "failure, expected_log",
        (
            (
                PermissionError(EACCES, "Permission denied"),
                (
                    logging.DEBUG,
                    (
                        "Using default instance-data/user-data paths for"
                        " non-root user"
                    ),
                ),
            ),
            (
                DataSourceNotFoundException("No cached datasource found yet"),
                (
                    logging.WARNING,
                    (
                        "datasource not detected, using default"
                        " instance-data/user-data paths."
                    ),
                ),
            ),
        ),
    )
    def test_system_falls_back_to_default_paths(
        self, m_read_cfg_paths, failure, expected_log, caplog, paths
    ):
        m_read_cfg_paths.side_effect = [failure, paths]
        args = Namespace(config_file=None, system=True)
        assert paths == schema.get_paths(args)
        assert [
            mock.call(fetch_existing_datasource="trust"),
            mock.call(),
        ] == m_read_cfg_paths.call_args_list
        assert ("cloudinit.cmd.schema", *expected_log) in caplog.record_tuples
