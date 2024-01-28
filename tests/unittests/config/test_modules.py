# This file is part of cloud-init. See LICENSE file for license information.


import importlib
import inspect
import logging
from pathlib import Path
from typing import List

import pytest

from cloudinit import util
from cloudinit.config.modules import ModuleDetails, Modules, _is_active
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import FREQUENCIES
from cloudinit.stages import Init
from tests.helpers import cloud_init_project_dir
from tests.unittests.helpers import mock

M_PATH = "cloudinit.config.modules."


def get_module_names() -> List[str]:
    """Return list of module names in cloudinit/config"""
    files = list(
        Path(cloud_init_project_dir("cloudinit/config/")).glob("cc_*.py"),
    )

    return [mod.stem for mod in files]


def get_modules():
    examples = []
    for mod_name in get_module_names():
        module = importlib.import_module(f"cloudinit.config.{mod_name}")
        for i, example in enumerate(module.meta.get("examples", [])):
            examples.append(
                pytest.param(
                    mod_name, module, example, id=f"{mod_name}_example_{i}"
                )
            )
    return examples


class TestModules:
    @pytest.mark.parametrize("frequency", FREQUENCIES)
    @pytest.mark.parametrize(
        "activate_by_schema_keys, cfg, active",
        [
            (None, {}, True),
            (None, {"module_name": {"x": "y"}}, True),
            ([], {"module_name": {"x": "y"}}, True),
            (["module_name"], {"module_name": {"x": "y"}}, True),
            (
                ["module_name", "other_module"],
                {"module_name": {"x": "y"}},
                True,
            ),
            (["module_name"], {"other_module": {"x": "y"}}, False),
            (
                ["x"],
                {"module_name": {"x": "y"}, "other_module": {"x": "y"}},
                False,
            ),
        ],
    )
    def test__is_inapplicable(
        self, activate_by_schema_keys, cfg, active, frequency
    ):
        module = mock.Mock()
        module.meta = MetaSchema(
            name="module_name",
            id="cc_module_name",
            title="title",
            description="description",
            distros=[ALL_DISTROS],
            examples=["example_0", "example_1"],
            frequency=frequency,
        )
        if activate_by_schema_keys is not None:
            module.meta["activate_by_schema_keys"] = activate_by_schema_keys
        module_details = ModuleDetails(
            module=module,
            name="name",
            frequency=frequency,
            run_args=[],
        )
        assert active == _is_active(module_details, cfg)

    @pytest.mark.parametrize("mod_name, module, example", get_modules())
    def test__is_inapplicable_examples(self, mod_name, module, example):
        module_details = ModuleDetails(
            module=module,
            name=mod_name,
            frequency=["always"],
            run_args=[],
        )
        assert True is _is_active(module_details, util.load_yaml(example))

    @pytest.mark.parametrize("frequency", FREQUENCIES)
    @pytest.mark.parametrize("active", [True, False])
    def test_run_section(self, frequency, active, caplog, mocker):
        mocker.patch(M_PATH + "_is_active", return_value=active)

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
        if active:
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

    @pytest.mark.parametrize("mod_name, module, example", get_modules())
    def test_run_section_examples(
        self, mod_name, module, example, caplog, mocker
    ):
        mods = Modules(
            init=mock.Mock(), cfg_files=mock.Mock(), reporter=mock.Mock()
        )
        cfg = util.load_yaml(example)
        cfg["unverified_modules"] = [mod_name]  # Force to run unverified mod
        mods._cached_cfg = cfg
        module_details = ModuleDetails(
            module=module,
            name=mod_name,
            frequency=["always"],
            run_args=[],
        )
        mocker.patch.object(
            mods,
            "_fixup_modules",
            return_value=[module_details],
        )
        mocker.patch.object(module, "handle")
        m_run_modules = mocker.patch.object(mods, "_run_modules")
        assert mods.run_section("not_matter")
        assert [
            mock.call([list(module_details)])
        ] == m_run_modules.call_args_list
        assert "Skipping" not in caplog.text

    @mock.patch(M_PATH + "signature")
    @mock.patch("cloudinit.config.modules.ReportEventStack")
    def test_old_handle(self, event, m_signature, caplog):
        def handle(name, cfg, cloud, log, args):
            pass

        m_signature.return_value = inspect.signature(handle)
        module = mock.Mock()
        module.handle.side_effect = handle
        mods = Modules(
            init=mock.Mock(spec=Init),
            cfg_files=mock.Mock(),
            reporter=mock.Mock(),
        )
        mods._cached_cfg = {}
        module_details = ModuleDetails(
            module=module,
            name="mod_name",
            frequency=["always"],
            run_args=[],
        )
        m_cc = mods.init.cloudify.return_value
        m_cc.run.return_value = (1, "doesnotmatter")

        mods._run_modules([module_details])

        assert [
            mock.call(
                mock.ANY,
                mock.ANY,
                {
                    "name": "mod_name",
                    "cfg": {},
                    "cloud": mock.ANY,
                    "args": [],
                    "log": mock.ANY,
                },
                freq=["always"],
            )
        ] == m_cc.run.call_args_list

        assert (
            "Config modules with a `log` parameter is deprecated in 23.2"
            in caplog.text
        )
