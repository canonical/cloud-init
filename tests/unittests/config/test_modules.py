# This file is part of cloud-init. See LICENSE file for license information.


import pytest

from cloudinit.config.modules import ModuleDetails, _is_inapplicable
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import FREQUENCIES
from tests.unittests.helpers import mock

M_PATH = "cloudinit.config.modules."


class TestModules:
    @pytest.mark.parametrize("frequency", FREQUENCIES)
    @pytest.mark.parametrize(
        "skip_by_schema, cfg, is_inapplicable",
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
        self, skip_by_schema, cfg, is_inapplicable, frequency
    ):
        module_meta = MetaSchema(
            name="module_name",
            id="cc_module_name",
            title="title",
            description="description",
            distros=["ubuntu"],
            examples=["example_0", "example_1"],
            frequency=frequency,
        )
        if skip_by_schema is not None:
            module_meta["skip_by_schema"] = skip_by_schema

        module = mock.Mock()
        module.meta = module_meta
        module_details = ModuleDetails(
            module=module,
            name="name",
            frequency=frequency,
            run_args=[],
        )
        assert is_inapplicable == _is_inapplicable(module_details, cfg)
