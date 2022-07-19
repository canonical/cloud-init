"""Integration test for the wireguard module.

TODO Description

"""
import pytest

from tests.integration_tests.instances import IntegrationInstance

WG1_CONTENT = """\
        [Interface]
        PrivateKey = GGLU4+5vIcK9lGyfz4AJn9fR5/FN/6sf4Fd5chZ16Vc=
        Address = 192.168.254.2/24
        ListenPort = 51820

        [Peer]
        PublicKey = 2as8z3EDjSsfFEkvOQGVnJ1Hv+h1jRAh2BKJg+DHvGk=
        Endpoint = 127.0.0.1:51820
        AllowedIPs = 0.0.0.0/0
"""

ASCII_TEXT = "ASCII text"

USER_DATA = """\
#cloud-config
wireguard:
  interfaces:
    - name: wg0
      config_path: /etc/wireguard/wg0.conf
      content: |
        [Interface]
        Address = 192.168.254.1/24
        ListenPort = 51820
        PrivateKey = iNlmgtGo6yiFhD9TuVnx/qJSp+C5Cwg4wwPmOJwlZXI=

        [Peer]
        PublicKey = 6PewunPjxlUq/0xvbVxklN2p73YIytfjxpoIEohCukY=
        AllowedIPs = 192.168.254.2/32
    - name: wg1
      config_path: /etc/wireguard/wg1.conf
      content: |
{}
""".format(
    WG1_CONTENT
)


@pytest.mark.ci
@pytest.mark.user_data(USER_DATA)
class TestWireguard:
    @pytest.mark.parametrize(
        "cmd,expected_out",
        (
            # test if file was written for wg0
            (
                "stat -c '%N' /etc/wireguard/wg0.conf",
                r"'/etc/wireguard/wg0.conf'",
            ),
            # check permissions for wg0
            ("stat -c '%U %a' /etc/wireguard/wg0.conf", r"root 600"),
            # ASCII check wg1
            ("file /etc/wireguard/wg1.conf", ASCII_TEXT),
            # md5sum check wg1
            (
                "md5sum </etc/wireguard/wg1.conf",
                "0e621de7a38ba4a8e2a8f0fe5b9cc6b5",
            ),
            # sha256sum check
            (
                "sha256sum </etc/wireguard/wg1.conf",
                "95cb51d9c343bee0a99f025402a0709e"
                "b9ac469a79c1f7f47fb846e81031b11a",
            ),
        ),
    )
    def test_wireguard(
        self, cmd, expected_out, class_client: IntegrationInstance
    ):
        out = class_client.execute(cmd)
        assert expected_out in out

    def test_wireguard_tools_installed(
        self, class_client: IntegrationInstance
    ):
        """Test that 'wg version' succeeds, indicating installation."""
        assert class_client.execute("wg version").ok

    def test_wireguard_systemd_running(
        self, class_client: IntegrationInstance
    ):
        return
