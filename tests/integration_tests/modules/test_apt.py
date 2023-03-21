"""Series of integration tests covering apt functionality."""
import re

import pytest

from cloudinit import gpg
from cloudinit.config import cc_apt_configure
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE, IS_UBUNTU

USER_DATA = """\
#cloud-config
apt:
  conf: |
    APT {
        Get {
            Assume-Yes "true";
            Fix-Broken "true";
        }
    }
  primary:
    - arches: [default]
      uri: http://badarchive.ubuntu.com/ubuntu
  security:
    - arches: [default]
      uri: http://badsecurity.ubuntu.com/ubuntu
  sources_list: |
    deb $MIRROR $RELEASE main restricted
    deb-src $MIRROR $RELEASE main restricted
    deb $PRIMARY $RELEASE universe restricted
    deb-src $PRIMARY $RELEASE universe restricted
    deb $SECURITY $RELEASE-security multiverse
    deb-src $SECURITY $RELEASE-security multiverse
  sources:
    test_keyserver:
      keyid: 110E21D8B0E2A1F0243AF6820856F197B892ACEA
      keyserver: keyserver.ubuntu.com
      source: "deb http://ppa.launchpad.net/canonical-kernel-team/ppa/ubuntu $RELEASE main"
    test_ppa:
      keyid: 441614D8
      keyserver: keyserver.ubuntu.com
      source: "ppa:simplestreams-dev/trunk"
    test_signed_by:
      keyid: A2EB2DEC0BD7519B7B38BE38376A290EC8068B11
      keyserver: keyserver.ubuntu.com
      source: "deb [signed-by=$KEY_FILE] http://ppa.launchpad.net/juju/stable/ubuntu $RELEASE main"
    test_bad_key:
      key: ""
      source: "deb $MIRROR $RELEASE main"
    test_key:
      source: "deb http://ppa.launchpad.net/cloud-init-dev/test-archive/ubuntu $RELEASE main"
      key: |
        -----BEGIN PGP PUBLIC KEY BLOCK-----
        Version: SKS 1.1.6
        Comment: Hostname: keyserver.ubuntu.com

        mQINBFbZRUIBEAC+A0PIKYBP9kLC4hQtRrffRS11uLo8/BdtmOdrlW0hpPHzCfKnjR3tvSEI
        lqPHG1QrrjAXKZDnZMRz+h/px7lUztvytGzHPSJd5ARUzAyjyRezUhoJ3VSCxrPqx62avuWf
        RfoJaIeHfDehL5/dTVkyiWxfVZ369ZX6JN2AgLsQTeybTQ75+2z0xPrrhnGmgh6g0qTYcAaq
        M5ONOGiqeSBX/Smjh6ALy5XkhUiFGLsI7Yluf6XSICY/x7gd6RAfgSIQrUTNMoS1sqhT4aot
        +xvOfQy8ySkfAK4NddXql6E/+ZqTmBY/Lr0YklFBy8jGT+UysfiIznPMIwbmgq5Li7BtDDtX
        b8Uyi4edPpjtextezfXYn4NVIpPL5dPZS/FXh4HpzyH0pYCfrH4QDGA7i52AGmhpiOFjJMo6
        N33sdjZHOH/2Vyp+QZaQnsdUAi1N4M6c33tQbpIScn1SY+El8z5JDA4PBzkw8HpLCi1gGoa6
        V4kfbWqXXbGAJFkLkP/vc4+pY9axOlmCkJg7xCPwhI75y1cONgovhz+BEXOzolh5KZuGbGbj
        xe0wva5DLBeIg7EQFf+99pOS7Syby3Xpm6ZbswEFV0cllK4jf/QMjtfInxobuMoI0GV0bE5l
        WlRtPCK5FnbHwxi0wPNzB/5fwzJ77r6HgPrR0OkT0lWmbUyoOQARAQABtC1MYXVuY2hwYWQg
        UFBBIGZvciBjbG91ZCBpbml0IGRldmVsb3BtZW50IHRlYW2JAjgEEwECACIFAlbZRUICGwMG
        CwkIBwMCBhUIAgkKCwQWAgMBAh4BAheAAAoJEAg9Bvvk0wTfHfcP/REK5N2s1JYc69qEa9ZN
        o6oi+A7l6AYw+ZY88O5TJe7F9otv5VXCIKSUT0Vsepjgf0mtXAgf/sb2lsJn/jp7tzgov3YH
        vSrkTkRydz8xcA87gwQKePuvTLxQpftF4flrBxgSueIn5O/tPrBOxLz7EVYBc78SKg9aj9L2
        yUp+YuNevlwfZCTYeBb9r3FHaab2HcgkwqYch66+nKYfwiLuQ9NzXXm0Wn0JcEQ6pWvJscbj
        C9BdawWovfvMK5/YLfI6Btm7F4mIpQBdhSOUp/YXKmdvHpmwxMCN2QhqYK49SM7qE9aUDbJL
        arppSEBtlCLWhRBZYLTUna+BkuQ1bHz4St++XTR49Qd7vDERALpApDjB2dxPfMiBzCMwQQyq
        uy13exU8o2ETLg+dZSLfDTzrBNsBFmXlw8WW17nTISYdKeGKL+QdlUjpzdwUMMzHhAO8SmMH
        zjeSlDSRMXBJFAFSbCl7EwmMKa3yVX0zInT91fNllZ3iatAmtVdqVH/BFQfTIMH2ET7A8WzJ
        ZzVSuMRhqoKdr5AMcHuJGPUoVkVJHQA+NNvEiXSysF3faL7jmKapmUwrhpYYX2H8pf+VMu2e
        cLflKTI28dl+ZQ4Pl/aVsxrti/pzhdYy05Sn5ddtySyIkvo8L1cU5MWpbvSlFPkTstBUDLBf
        pb0uBy+g0oxJQg15
        =uy53
        -----END PGP PUBLIC KEY BLOCK-----
    test_write:
      keyid: A2EB2DEC0BD7519B7B38BE38376A290EC8068B11
      keyserver: keyserver.ubuntu.com
      source: "deb [signed-by=$KEY_FILE] http://ppa.launchpad.net/juju/stable/ubuntu $RELEASE main"
      append: false
    test_write.list:
      keyid: A2EB2DEC0BD7519B7B38BE38376A290EC8068B11
      keyserver: keyserver.ubuntu.com
      source: "deb [signed-by=$KEY_FILE] http://ppa.launchpad.net/juju/devel/ubuntu $RELEASE main"
      append: false
    test_append:
      keyid: A2EB2DEC0BD7519B7B38BE38376A290EC8068B11
      keyserver: keyserver.ubuntu.com
      source: "deb [signed-by=$KEY_FILE] http://ppa.launchpad.net/juju/stable/ubuntu $RELEASE main"
    test_append.list:
      keyid: A2EB2DEC0BD7519B7B38BE38376A290EC8068B11
      keyserver: keyserver.ubuntu.com
      source: "deb [signed-by=$KEY_FILE] http://ppa.launchpad.net/juju/devel/ubuntu $RELEASE main"
apt_pipelining: os
"""  # noqa: E501

EXPECTED_REGEXES = [
    r"deb http://badarchive.ubuntu.com/ubuntu [a-z]+ main restricted",
    r"deb-src http://badarchive.ubuntu.com/ubuntu [a-z]+ main restricted",
    r"deb http://badarchive.ubuntu.com/ubuntu [a-z]+ universe restricted",
    r"deb-src http://badarchive.ubuntu.com/ubuntu [a-z]+ universe restricted",
    r"deb http://badsecurity.ubuntu.com/ubuntu [a-z]+-security multiverse",
    r"deb-src http://badsecurity.ubuntu.com/ubuntu [a-z]+-security multiverse",
]

TEST_KEYSERVER_KEY = "110E 21D8 B0E2 A1F0 243A  F682 0856 F197 B892 ACEA"
TEST_PPA_KEY = "3552 C902 B4DD F7BD 3842  1821 015D 28D7 4416 14D8"
TEST_KEY = "1FF0 D853 5EF7 E719 E5C8  1B9C 083D 06FB E4D3 04DF"
TEST_SIGNED_BY_KEY = "A2EB 2DEC 0BD7 519B 7B38  BE38 376A 290E C806 8B11"


@pytest.mark.skipif(not IS_UBUNTU, reason="Apt usage")
@pytest.mark.user_data(USER_DATA)
class TestApt:
    def get_keys(self, class_client: IntegrationInstance):
        """Return all keys in /etc/apt/trusted.gpg.d/ and /etc/apt/trusted.gpg
        in human readable format. Mimics the output of apt-key finger
        """
        list_cmd = " ".join(gpg.GPG_LIST) + " "
        keys = class_client.execute(list_cmd + cc_apt_configure.APT_LOCAL_KEYS)
        print(keys)
        files = class_client.execute(
            "ls " + cc_apt_configure.APT_TRUSTED_GPG_DIR
        )
        for file in files.split():
            path = cc_apt_configure.APT_TRUSTED_GPG_DIR + file
            keys += class_client.execute(list_cmd + path) or ""
        return keys

    def test_sources_list(self, class_client: IntegrationInstance):
        """Integration test for the apt module's `sources_list` functionality.

        This test specifies a ``sources_list`` and then checks that (a) the
        expected number of sources.list entries is present, and (b) that each
        expected line appears in the file.

        (This is ported from
        `tests/cloud_tests/testcases/modules/apt_configure_sources_list.yaml`.)
        """
        sources_list = class_client.read_from_file("/etc/apt/sources.list")
        assert 6 == len(sources_list.rstrip().split("\n"))

        for expected_re in EXPECTED_REGEXES:
            assert re.search(expected_re, sources_list) is not None

    def test_apt_conf(self, class_client: IntegrationInstance):
        """Test the apt conf functionality.

        Ported from tests/cloud_tests/testcases/modules/apt_configure_conf.py
        """
        apt_config = class_client.read_from_file(
            "/etc/apt/apt.conf.d/94cloud-init-config"
        )
        assert 'Assume-Yes "true";' in apt_config
        assert 'Fix-Broken "true";' in apt_config

    def test_ppa_source(self, class_client: IntegrationInstance):
        """Test the apt ppa functionality.

        Ported from
        tests/cloud_tests/testcases/modules/apt_configure_sources_ppa.py
        """
        ppa_path_contents = class_client.read_from_file(
            "/etc/apt/sources.list.d/"
            "simplestreams-dev-ubuntu-trunk-{}.list".format(
                CURRENT_RELEASE.series
            )
        )
        assert (
            "://ppa.launchpad.net/simplestreams-dev/trunk/ubuntu"
            in ppa_path_contents
            or "://ppa.launchpadcontent.net/simplestreams-dev/trunk/ubuntu"
            in ppa_path_contents
        )

        assert TEST_PPA_KEY in self.get_keys(class_client)

    def test_signed_by(self, class_client: IntegrationInstance):
        """Test the apt signed-by functionality."""
        source = (
            "deb [signed-by=/etc/apt/cloud-init.gpg.d/test_signed_by.gpg] "
            "http://ppa.launchpad.net/juju/stable/ubuntu"
            " {} main".format(CURRENT_RELEASE.series)
        )
        path_contents = class_client.read_from_file(
            "/etc/apt/sources.list.d/test_signed_by.list"
        )
        assert path_contents == source

        key = class_client.execute(
            "gpg --no-default-keyring --with-fingerprint --list-keys "
            "--keyring /etc/apt/cloud-init.gpg.d/test_signed_by.gpg"
        )

        assert TEST_SIGNED_BY_KEY in key

    def test_bad_key(self, class_client: IntegrationInstance):
        """Test the apt signed-by functionality."""
        with pytest.raises(OSError):
            class_client.read_from_file(
                "/etc/apt/trusted.list.d/test_bad_key.gpg"
            )

    def test_key(self, class_client: IntegrationInstance):
        """Test the apt key functionality.

        Ported from
        tests/cloud_tests/testcases/modules/apt_configure_sources_key.py
        """
        test_archive_contents = class_client.read_from_file(
            "/etc/apt/sources.list.d/test_key.list"
        )

        assert (
            "http://ppa.launchpad.net/cloud-init-dev/test-archive/ubuntu"
            in test_archive_contents
        )
        assert TEST_KEY in self.get_keys(class_client)

    def test_keyserver(self, class_client: IntegrationInstance):
        """Test the apt keyserver functionality.

        Ported from
        tests/cloud_tests/testcases/modules/apt_configure_sources_keyserver.py
        """
        test_keyserver_contents = class_client.read_from_file(
            "/etc/apt/sources.list.d/test_keyserver.list"
        )

        assert (
            "http://ppa.launchpad.net/canonical-kernel-team/ppa/ubuntu"
            in test_keyserver_contents
        )

        assert TEST_KEYSERVER_KEY in self.get_keys(class_client)

    def test_os_pipelining(self, class_client: IntegrationInstance):
        """Test 'os' settings does not write apt config file.

        Ported from tests/cloud_tests/testcases/modules/apt_pipelining_os.py
        """
        conf_exists = class_client.execute(
            "test -f /etc/apt/apt.conf.d/90cloud-init-pipelining"
        ).ok
        assert conf_exists is False

    def test_sources_write(self, class_client: IntegrationInstance):
        """Test overwrite or append to sources file"""
        test_write_content = class_client.read_from_file(
            "/etc/apt/sources.list.d/test_write.list"
        )
        expected_contents = (
            "deb [signed-by=/etc/apt/cloud-init.gpg.d/test_write.gpg] "
            "http://ppa.launchpad.net/juju/devel/ubuntu "
            f"{CURRENT_RELEASE.series} main"
        )
        assert expected_contents.strip() == test_write_content.strip()

    def test_sources_append(self, class_client: IntegrationInstance):
        series = CURRENT_RELEASE.series
        test_append_content = class_client.read_from_file(
            "/etc/apt/sources.list.d/test_append.list"
        )

        expected_contents = (
            "deb [signed-by=/etc/apt/cloud-init.gpg.d/test_append.gpg] "
            f"http://ppa.launchpad.net/juju/stable/ubuntu {series} main\n"
            "deb [signed-by=/etc/apt/cloud-init.gpg.d/test_append.gpg] "
            f"http://ppa.launchpad.net/juju/devel/ubuntu {series} main"
        )
        assert expected_contents.strip() == test_append_content.strip()


_DEFAULT_DATA = """\
#cloud-config
apt:
  primary:
    - arches:
      - default
      {uri}
  security:
    - arches:
      - default
"""
DEFAULT_DATA = _DEFAULT_DATA.format(uri="")


@pytest.mark.skipif(not IS_UBUNTU, reason="Apt usage")
@pytest.mark.user_data(DEFAULT_DATA)
class TestDefaults:
    @pytest.mark.skipif(
        PLATFORM != "openstack", reason="Test is Openstack specific"
    )
    def test_primary_on_openstack(self, class_client: IntegrationInstance):
        """Test apt default primary source on openstack.

        When no uri is provided.
        """
        zone = class_client.execute("cloud-init query v1.availability_zone")
        sources_list = class_client.read_from_file("/etc/apt/sources.list")
        assert "{}.clouds.archive.ubuntu.com".format(zone) in sources_list

    def test_security(self, class_client: IntegrationInstance):
        """Test apt default security sources.

        Ported from
        tests/cloud_tests/testcases/modules/apt_configure_security.py
        """
        sources_list = class_client.read_from_file("/etc/apt/sources.list")

        # 3 lines from main, universe, and multiverse
        series = CURRENT_RELEASE.series
        sec_url = f"deb http://security.ubuntu.com/ubuntu {series}-security"
        if class_client.settings.PLATFORM == "azure":
            sec_url = (
                f"deb http://azure.archive.ubuntu.com/ubuntu/"
                f" {series}-security"
            )
        sec_src_url = sec_url.replace("deb ", "# deb-src ")
        assert 3 == sources_list.count(sec_url)
        assert 3 == sources_list.count(sec_src_url)


DEFAULT_DATA_WITH_URI = _DEFAULT_DATA.format(
    uri='uri: "http://something.random.invalid/ubuntu"'
)


@pytest.mark.user_data(DEFAULT_DATA_WITH_URI)
def test_default_primary_with_uri(client: IntegrationInstance):
    """Test apt default primary sources.

    Ported from
    tests/cloud_tests/testcases/modules/apt_configure_primary.py
    """
    sources_list = client.read_from_file("/etc/apt/sources.list")
    assert "archive.ubuntu.com" not in sources_list

    assert "something.random.invalid" in sources_list


DISABLED_DATA = """\
#cloud-config
apt:
  disable_suites:
  - $RELEASE
  - $RELEASE-updates
  - $RELEASE-backports
  - $RELEASE-security
apt_pipelining: false
"""


@pytest.mark.skipif(not IS_UBUNTU, reason="Apt usage")
@pytest.mark.user_data(DISABLED_DATA)
class TestDisabled:
    def test_disable_suites(self, class_client: IntegrationInstance):
        """Test disabling of apt suites.

        Ported from
        tests/cloud_tests/testcases/modules/apt_configure_disable_suites.py
        """
        sources_list = class_client.execute(
            "cat /etc/apt/sources.list | grep -v '^#'"
        ).strip()
        assert "" == sources_list

    def test_disable_apt_pipelining(self, class_client: IntegrationInstance):
        """Test disabling of apt pipelining.

        Ported from
        tests/cloud_tests/testcases/modules/apt_pipelining_disable.py
        """
        conf = class_client.read_from_file(
            "/etc/apt/apt.conf.d/90cloud-init-pipelining"
        )
        assert 'Acquire::http::Pipeline-Depth "0";' in conf


APT_PROXY_DATA = """\
#cloud-config
apt:
  proxy: "http://proxy.internal:3128"
  http_proxy: "http://squid.internal:3128"
  ftp_proxy: "ftp://squid.internal:3128"
  https_proxy: "https://squid.internal:3128"
"""


@pytest.mark.skipif(not IS_UBUNTU, reason="Apt usage")
@pytest.mark.user_data(APT_PROXY_DATA)
def test_apt_proxy(client: IntegrationInstance):
    """Test the apt proxy data gets written correctly."""
    out = client.read_from_file("/etc/apt/apt.conf.d/90cloud-init-aptproxy")
    assert 'Acquire::http::Proxy "http://proxy.internal:3128";' in out
    assert 'Acquire::http::Proxy "http://squid.internal:3128";' in out
    assert 'Acquire::ftp::Proxy "ftp://squid.internal:3128";' in out
    assert 'Acquire::https::Proxy "https://squid.internal:3128";' in out
