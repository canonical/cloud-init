import os
from unittest import mock

import pytest

from cloudinit import util
from cloudinit.net import netplan


@pytest.fixture
def renderer(tmp_path):
    config = {
        "netplan_path": str(tmp_path / "netplan/50-cloud-init.yaml"),
        "postcmds": True,
    }
    yield netplan.Renderer(config)


class TestNetplanRenderer:
    @pytest.mark.parametrize("write_config", [True, False])
    def test_skip_netplan_generate(self, renderer, write_config, mocker):
        """Check `netplan generate` is called if netplan config has changed."""
        header = "\n"
        content = "foo"
        renderer_mocks = mocker.patch.multiple(
            renderer,
            _render_content=mocker.Mock(return_value=content),
            _netplan_generate=mocker.DEFAULT,
            _net_setup_link=mocker.DEFAULT,
        )
        if write_config:
            util.ensure_dir(os.path.dirname(renderer.netplan_path))
            with open(renderer.netplan_path, "w") as f:
                f.write(header)
                f.write(content)

        renderer.render_network_state(mocker.Mock())

        assert renderer_mocks["_netplan_generate"].call_args_list == [
            mock.call(run=True, same_content=write_config)
        ]
