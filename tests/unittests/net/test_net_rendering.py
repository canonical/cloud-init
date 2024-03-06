"""Home of the tests for end-to-end net rendering

Tests defined here should take a v1 or v2 yaml config as input, and verify
that the rendered network config is as expected. Input files are defined
under `tests/unittests/net/artifacts` with the format of

<test_name><format>.yaml

For example, if my test name is "test_all_the_things" and I'm testing a
v2 format, I should have a file named test_all_the_things_v2.yaml.

If a renderer outputs multiple files, the expected files should live in
the artifacts directory under the given test name. For example, if I'm
expecting NetworkManager to output a file named eth0.nmconnection as
part of my "test_all_the_things" test, then in the artifacts directory
there should be a
`test_all_the_things/etc/NetworkManager/system-connections/eth0.nmconnection`
file.

To add a new nominal test, create the input and output files, then add the test
name to the `test_convert` test along with it's supported renderers.

Before adding a test here, check that it is not already represented
in `unittests/test_net.py`. While that file contains similar tests, it has
become too large to be maintainable.
"""
import glob
from enum import Flag, auto
from pathlib import Path

import pytest

from cloudinit import safeyaml
from cloudinit.net.netplan import Renderer as NetplanRenderer
from cloudinit.net.network_manager import Renderer as NetworkManagerRenderer
from cloudinit.net.network_state import NetworkState, parse_net_config_data

ARTIFACT_DIR = Path(__file__).parent.absolute() / "artifacts"


class Renderer(Flag):
    Netplan = auto()
    NetworkManager = auto()
    Networkd = auto()


@pytest.fixture(autouse=True)
def setup(mocker):
    mocker.patch("cloudinit.net.network_state.get_interfaces_by_mac")


def _check_netplan(
    network_state: NetworkState, netplan_path: Path, expected_config
):
    if network_state.version == 2:
        renderer = NetplanRenderer(config={"netplan_path": netplan_path})
        renderer.render_network_state(network_state)
        assert safeyaml.load(netplan_path.read_text()) == expected_config, (
            f"Netplan config generated at {netplan_path} does not match v2 "
            "config defined for this test."
        )
    else:
        raise NotImplementedError


def _check_network_manager(network_state: NetworkState, tmp_path: Path):
    renderer = NetworkManagerRenderer()
    renderer.render_network_state(
        network_state, target=str(tmp_path / "no_matching_mac")
    )
    expected_paths = glob.glob(
        str(ARTIFACT_DIR / "no_matching_mac" / "**/*.nmconnection"),
        recursive=True,
    )
    for expected_path in expected_paths:
        expected_contents = Path(expected_path).read_text()
        actual_path = tmp_path / expected_path.split(
            str(ARTIFACT_DIR), maxsplit=1
        )[1].lstrip("/")
        assert (
            actual_path.exists()
        ), f"Expected {actual_path} to exist, but it does not"
        actual_contents = actual_path.read_text()
        assert expected_contents.strip() == actual_contents.strip()


@pytest.mark.parametrize(
    "test_name, renderers",
    [("no_matching_mac_v2", Renderer.Netplan | Renderer.NetworkManager)],
)
def test_convert(test_name, renderers, tmp_path):
    network_config = safeyaml.load(
        Path(ARTIFACT_DIR, f"{test_name}.yaml").read_text()
    )
    network_state = parse_net_config_data(network_config["network"])
    if Renderer.Netplan in renderers:
        _check_netplan(
            network_state, tmp_path / "netplan.yaml", network_config
        )
    if Renderer.NetworkManager in renderers:
        _check_network_manager(network_state, tmp_path)
