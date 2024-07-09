# This file is part of cloud-init. See LICENSE file for license information.
"""Series of integration tests covering apt functionality."""
import re
from textwrap import dedent

import pytest

from cloudinit.config import cc_apt_configure
from cloudinit.util import is_true
from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE, IS_UBUNTU
from tests.integration_tests.util import (
    get_feature_flag_value,
    verify_clean_log,
)

DEB822_SOURCES_FILE = "/etc/apt/sources.list.d/ubuntu.sources"
ORIG_SOURCES_FILE = "/etc/apt/sources.list"
GET_TEMPDIR = "python3 -c 'import tempfile;print(tempfile.mkdtemp());'"

USER_DATA = """\
#cloud-config
bootcmd:
    - rm -f /etc/apt/sources.list /etc/apt/sources.list.d/ubuntu.sources

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
      keyid: 1BC30F715A3B861247A81A5E55FE7C8C0165013E
      keyserver: keyserver.ubuntu.com
      # Hard-code noble as devel releases may not see new packages for some time
      source: "deb http://ppa.launchpad.net/curtin-dev/daily/ubuntu noble main"
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

TEST_KEYSERVER_KEY = "1BC3 0F71 5A3B 8612 47A8  1A5E 55FE 7C8C 0165 013E"
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
        class_client.execute("mkdir /root/tmpdir && chmod &00 /root/tmpdir")
        GPG_LIST = [
            "gpg",
            "--no-options",
            "--with-fingerprint",
            "--homedir /root/tmpdir",
            "--no-default-keyring",
            "--list-keys",
            "--keyring",
        ]

        list_cmd = " ".join(GPG_LIST) + " "
        keys = class_client.execute(list_cmd + cc_apt_configure.APT_LOCAL_KEYS)
        files = class_client.execute(
            "ls " + cc_apt_configure.APT_TRUSTED_GPG_DIR
        ).stdout
        for file in files.split():
            path = cc_apt_configure.APT_TRUSTED_GPG_DIR + file
            keys += class_client.execute(list_cmd + path).stdout
        class_client.execute("gpgconf --homedir /root/tmpdir --kill all")
        return keys

    def test_sources_list(self, class_client: IntegrationInstance):
        """Integration test for the apt module's `sources_list` functionality.

        This test specifies a ``sources_list`` and then checks that (a) the
        expected number of sources.list entries is present, and (b) that each
        expected line appears in the file.

        Since sources_list is no deb822-compliant, ORIG_SOURCES_FILE will
        always be written regardless of feature.APT_DEB822_SOURCE_LIST_FILE
        """
        sources_list = class_client.read_from_file(ORIG_SOURCES_FILE)
        assert 6 == len(sources_list.rstrip().split("\n"))
        for expected_re in EXPECTED_REGEXES:
            assert re.search(expected_re, sources_list) is not None

    def test_apt_conf(self, class_client: IntegrationInstance):
        """Test the apt conf functionality."""
        apt_config = class_client.read_from_file(
            "/etc/apt/apt.conf.d/94cloud-init-config"
        )
        assert 'Assume-Yes "true";' in apt_config
        assert 'Fix-Broken "true";' in apt_config

    def test_ppa_source(self, class_client: IntegrationInstance):
        """Test the apt ppa functionality."""
        ppa_path = (
            "/etc/apt/sources.list.d/simplestreams-dev-ubuntu-trunk-{}".format(
                CURRENT_RELEASE.series
            )
        )
        if CURRENT_RELEASE.series < "mantic":
            ppa_path += ".list"
        else:
            ppa_path += ".sources"
        ppa_path_contents = class_client.read_from_file(ppa_path)
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

        temp = class_client.execute(GET_TEMPDIR)
        key = class_client.execute(
            f"gpg --no-options --homedir {temp} --no-default-keyring "
            "--with-fingerprint --list-keys "
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
        """Test the apt key functionality."""
        test_archive_contents = class_client.read_from_file(
            "/etc/apt/sources.list.d/test_key.list"
        )

        assert (
            "http://ppa.launchpad.net/cloud-init-dev/test-archive/ubuntu"
            in test_archive_contents
        )
        assert TEST_KEY in self.get_keys(class_client)

    def test_keyserver(self, class_client: IntegrationInstance):
        """Test the apt keyserver functionality."""
        test_keyserver_contents = class_client.read_from_file(
            "/etc/apt/sources.list.d/test_keyserver.list"
        )

        assert (
            "http://ppa.launchpad.net/curtin-dev/daily/ubuntu"
            in test_keyserver_contents
        )

        assert TEST_KEYSERVER_KEY in self.get_keys(class_client)

    def test_os_pipelining(self, class_client: IntegrationInstance):
        """Test 'os' settings does not write apt config file."""
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
        feature_deb822 = is_true(
            get_feature_flag_value(class_client, "APT_DEB822_SOURCE_LIST_FILE")
        )
        src_file = DEB822_SOURCES_FILE if feature_deb822 else ORIG_SOURCES_FILE
        sources_list = class_client.read_from_file(src_file)
        assert "{}.clouds.archive.ubuntu.com".format(zone) in sources_list

    def test_security(self, class_client: IntegrationInstance):
        """Test apt default security sources."""
        series = CURRENT_RELEASE.series
        feature_deb822 = is_true(
            get_feature_flag_value(class_client, "APT_DEB822_SOURCE_LIST_FILE")
        )
        if class_client.settings.PLATFORM == "azure":
            sec_url = "http://azure.archive.ubuntu.com/ubuntu/"
        else:
            sec_url = "http://security.ubuntu.com/ubuntu"
        if feature_deb822:
            expected_cfg = dedent(
                f"""\
                Types: deb
                URIs: {sec_url}
                Suites: {series}-security
                """
            )
            sources_list = class_client.read_from_file(DEB822_SOURCES_FILE)
            assert expected_cfg in sources_list
        else:
            sources_list = class_client.read_from_file(ORIG_SOURCES_FILE)
            # 3 lines from main, universe, and multiverse
            sec_deb_line = f"deb {sec_url} {series}-security"
            sec_src_deb_line = sec_deb_line.replace("deb ", "# deb-src ")
            assert 3 == sources_list.count(sec_deb_line)
            assert 3 == sources_list.count(sec_src_deb_line)

    def test_no_duplicate_apt_sources(self, class_client: IntegrationInstance):
        r = class_client.execute("apt-get update", use_sudo=True)
        assert not re.match(
            r"^W: Target Packages .+ is configured multiple times in", r.stderr
        )

    def test_disabled_apt_sources(self, class_client: IntegrationInstance):
        feature_deb822 = is_true(
            get_feature_flag_value(class_client, "APT_DEB822_SOURCE_LIST_FILE")
        )
        if feature_deb822:

            assert (
                cc_apt_configure.UBUNTU_DEFAULT_APT_SOURCES_LIST.strip()
                == class_client.read_from_file(ORIG_SOURCES_FILE)
            )


DEFAULT_DATA_WITH_URI = _DEFAULT_DATA.format(
    uri='uri: "http://something.random.invalid/ubuntu"'
)


@pytest.mark.user_data(DEFAULT_DATA_WITH_URI)
def test_default_primary_with_uri(client: IntegrationInstance):
    """Test apt default primary sources."""
    feature_deb822 = is_true(
        get_feature_flag_value(client, "APT_DEB822_SOURCE_LIST_FILE")
    )
    src_file = DEB822_SOURCES_FILE if feature_deb822 else ORIG_SOURCES_FILE
    sources_list = client.read_from_file(src_file)
    assert "archive.ubuntu.com" not in sources_list
    assert "something.random.invalid" in sources_list


DISABLED_DATA = """\
#cloud-config
bootcmd: [mkdir -p /etc/apt/sources.new.d]
apt:
  conf: |
    Dir::Etc::sourceparts "sources.new.d";
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
        """Test disabling of apt suites."""
        feature_deb822 = is_true(
            get_feature_flag_value(class_client, "APT_DEB822_SOURCE_LIST_FILE")
        )
        if feature_deb822:
            # DISABLED_DATA changes Dir:Etc::sourceparts to sources.new.d
            src_file = DEB822_SOURCES_FILE.replace("list", "new")
        else:
            src_file = ORIG_SOURCES_FILE
        sources_list = class_client.execute(
            f"cat {src_file} | grep -v '^#'"
        ).strip()
        assert "" == sources_list

    def test_disable_apt_pipelining(self, class_client: IntegrationInstance):
        """Test disabling of apt pipelining."""
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


INSTALL_ANY_MISSING_RECOMMENDED_DEPENDENCIES = """\
#cloud-config
apt:
  sources:
    test_keyserver:
      keyid: 1BC30F715A3B861247A81A5E55FE7C8C0165013E
      keyserver: keyserver.ubuntu.com
      # Hard-code noble as devel releases may not see new packages for some time
      source: "deb http://ppa.launchpad.net/curtin-dev/daily/ubuntu noble main"
    test_ppa:
      keyid: 441614D8
      keyserver: keyserver.ubuntu.com
      source: "ppa:simplestreams-dev/trunk"
"""  # noqa: E501


RE_GPG_SW_PROPERTIES_INSTALLED = (
    r"install"
    r" (gnupg software-properties-common|software-properties-common gnupg)"
)

REMOVE_GPG_USERDATA = """
#cloud-config
runcmd:
  - DEBIAN_FRONTEND=noninteractive apt-get remove gpg -y
"""


@pytest.mark.skipif(not IS_UBUNTU, reason="Apt usage")
def test_install_missing_deps(setup_image, session_cloud: IntegrationCloud):
    # Two stage install: First stage:  remove gpg noninteractively from image
    instance1 = session_cloud.launch(user_data=REMOVE_GPG_USERDATA)
    snapshot_id = instance1.snapshot()
    instance1.destroy()
    # Second stage: provide active apt user-data which will install missing gpg
    with session_cloud.launch(
        user_data=INSTALL_ANY_MISSING_RECOMMENDED_DEPENDENCIES,
        launch_kwargs={"image_id": snapshot_id},
    ) as minimal_client:
        log = minimal_client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)
        assert re.search(RE_GPG_SW_PROPERTIES_INSTALLED, log)
