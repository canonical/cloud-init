# This file is part of cloud-init. See LICENSE file for license information.


import logging

import pytest

from cloudinit.config.modules import ModuleDetails, Modules, _is_inapplicable
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import FREQUENCIES
from tests.unittests.helpers import mock

M_PATH = "cloudinit.config.modules."


class TestModules:
    @pytest.mark.parametrize("frequency", FREQUENCIES)
    @pytest.mark.parametrize(
        "activate_by_schema_keys, cfg, is_inapplicable",
        [
            (None, {}, False),
            (None, {"module_name": {"x": "y"}}, False),
            ([], {"module_name": {"x": "y"}}, False),
            (["module_name"], {"module_name": {"x": "y"}}, False),
            (
                ["module_name", "other_module"],
                {"module_name": {"x": "y"}},
                False,
            ),
            (["module_name"], {"other_module": {"x": "y"}}, True),
            (
                ["x"],
                {"module_name": {"x": "y"}, "other_module": {"x": "y"}},
                True,
            ),
        ],
    )
    def test__is_inapplicable(
        self, activate_by_schema_keys, cfg, is_inapplicable, frequency
    ):
        module_meta = MetaSchema(
            name="module_name",
            id="cc_module_name",
            title="title",
            description="description",
            distros=[ALL_DISTROS],
            examples=["example_0", "example_1"],
            frequency=frequency,
        )
        if activate_by_schema_keys is not None:
            module_meta["activate_by_schema_keys"] = activate_by_schema_keys

        module = mock.Mock()
        module.meta = module_meta
        module_details = ModuleDetails(
            module=module,
            name="name",
            frequency=frequency,
            run_args=[],
        )
        assert is_inapplicable == _is_inapplicable(module_details, cfg)

    @pytest.mark.parametrize("frequency", FREQUENCIES)
    @pytest.mark.parametrize("is_inapplicable", [True, False])
    def test_run_section(self, frequency, is_inapplicable, caplog, mocker):
        mocker.patch(M_PATH + "_is_inapplicable", return_value=is_inapplicable)

        mods = Modules(
            init=mock.Mock(), cfg_files=mock.Mock(), reporter=mock.Mock()
        )
        mods._cached_cfg = {}
        raw_name = "my_module"
        module = mock.Mock()
        module.meta = MetaSchema(
            name=raw_name,
            id=f"cc_{raw_name}",
            title="title",
            description="description",
            distros=[ALL_DISTROS],
            examples=["example_0", "example_1"],
            frequency=frequency,
        )
        module_details = ModuleDetails(
            module=module,
            name=raw_name,
            frequency=frequency,
            run_args=["<arg>"],
        )
        mocker.patch.object(
            mods,
            "_fixup_modules",
            return_value=[module_details],
        )
        m_run_modules = mocker.patch.object(mods, "_run_modules")

        assert mods.run_section("not_matter")
        if not is_inapplicable:
            assert [
                mock.call([list(module_details)])
            ] == m_run_modules.call_args_list
            assert not caplog.text
        else:
            assert [mock.call([])] == m_run_modules.call_args_list
            assert (
                logging.INFO,
                (
                    f"Skipping modules '{raw_name}' because no applicable"
                    " config is provided."
                ),
            ) == caplog.record_tuples[-1][1:]
