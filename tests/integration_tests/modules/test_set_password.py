"""Integration test for the set_password module.

This test specifies a combination of user/password pairs, and ensures that the
system has the correct passwords set.

There are two tests run here: one tests chpasswd's list being a YAML list, the
other tests chpasswd's list being a string.  Both expect the same results, so
they use a mixin to share their test definitions, because we can (of course)
only specify one user-data per instance.
"""
import crypt

import pytest
import yaml


COMMON_USER_DATA = """\
#cloud-config
ssh_pwauth: yes
users:
  - default
  - name: tom
    # md5 gotomgo
    passwd: "$1$S7$tT1BEDIYrczeryDQJfdPe0"
    lock_passwd: false
  - name: dick
    # md5 gocubsgo
    passwd: "$1$ssisyfpf$YqvuJLfrrW6Cg/l53Pi1n1"
    lock_passwd: false
  - name: harry
    # sha512 goharrygo
    passwd: "$6$LF$9Z2p6rWK6TNC1DC6393ec0As.18KRAvKDbfsGJEdWN3sRQRwpdfoh37EQ3y\
Uh69tP4GSrGW5XKHxMLiKowJgm/"
    lock_passwd: false
  - name: jane
    # sha256 gojanego
    passwd: "$5$iW$XsxmWCdpwIW8Yhv.Jn/R3uk6A4UaicfW5Xp7C9p9pg."
    lock_passwd: false
  - name: "mikey"
    lock_passwd: false
"""

LIST_USER_DATA = COMMON_USER_DATA + """
chpasswd:
  list:
    - tom:mypassword123!
    - dick:RANDOM
    - harry:RANDOM
    - mikey:$5$xZ$B2YGGEx2AOf4PeW48KC6.QyT1W2B4rZ9Qbltudtha89
"""

STRING_USER_DATA = COMMON_USER_DATA + """
chpasswd:
    list: |
      tom:mypassword123!
      dick:RANDOM
      harry:RANDOM
      mikey:$5$xZ$B2YGGEx2AOf4PeW48KC6.QyT1W2B4rZ9Qbltudtha89
"""

USERS_DICTS = yaml.safe_load(COMMON_USER_DATA)["users"]
USERS_PASSWD_VALUES = {
    user_dict["name"]: user_dict["passwd"]
    for user_dict in USERS_DICTS
    if "name" in user_dict and "passwd" in user_dict
}


class Mixin:
    """Shared test definitions."""

    def _fetch_and_parse_etc_shadow(self, class_client):
        """Fetch /etc/shadow and parse it into Python data structures

        Returns: ({user: password}, [duplicate, users])
        """
        shadow_content = class_client.read_from_file("/etc/shadow")
        users = {}
        dupes = []
        for line in shadow_content.splitlines():
            user, encpw = line.split(":")[0:2]
            if user in users:
                dupes.append(user)
            users[user] = encpw
        return users, dupes

    def test_no_duplicate_users_in_shadow(self, class_client):
        """Confirm that set_passwords has not added duplicate shadow entries"""
        _, dupes = self._fetch_and_parse_etc_shadow(class_client)

        assert [] == dupes

    def test_password_in_users_dict_set_correctly(self, class_client):
        """Test that the password specified in the users dict is set."""
        shadow_users, _ = self._fetch_and_parse_etc_shadow(class_client)
        assert USERS_PASSWD_VALUES["jane"] == shadow_users["jane"]

    def test_password_in_chpasswd_list_set_correctly(self, class_client):
        """Test that a chpasswd password overrides one in the users dict."""
        shadow_users, _ = self._fetch_and_parse_etc_shadow(class_client)
        mikey_hash = "$5$xZ$B2YGGEx2AOf4PeW48KC6.QyT1W2B4rZ9Qbltudtha89"
        assert mikey_hash == shadow_users["mikey"]

    def test_random_passwords_set_correctly(self, class_client):
        """Test that RANDOM chpasswd entries replace users dict passwords."""
        shadow_users, _ = self._fetch_and_parse_etc_shadow(class_client)

        # These should have been changed
        assert shadow_users["harry"] != USERS_PASSWD_VALUES["harry"]
        assert shadow_users["dick"] != USERS_PASSWD_VALUES["dick"]

        # To random passwords
        assert shadow_users["harry"].startswith("$")
        assert shadow_users["dick"].startswith("$")

        # Which are not the same
        assert shadow_users["harry"] != shadow_users["dick"]

    def test_random_passwords_not_stored_in_cloud_init_output_log(
        self, class_client
    ):
        """We should not emit passwords to the in-instance log file.

        LP: #1918303
        """
        cloud_init_output = class_client.read_from_file(
            "/var/log/cloud-init-output.log"
        )
        assert "dick:" not in cloud_init_output
        assert "harry:" not in cloud_init_output

    def test_random_passwords_emitted_to_serial_console(self, class_client):
        """We should emit passwords to the serial console. (LP: #1918303)"""
        try:
            console_log = class_client.instance.console_log()
        except NotImplementedError:
            # Assume that an exception here means that we can't use the console
            # log
            pytest.skip("NotImplementedError when requesting console log")
        assert "dick:" in console_log
        assert "harry:" in console_log

    def test_explicit_password_set_correctly(self, class_client):
        """Test that an explicitly-specified password is set correctly."""
        shadow_users, _ = self._fetch_and_parse_etc_shadow(class_client)

        fmt_and_salt = shadow_users["tom"].rsplit("$", 1)[0]
        expected_value = crypt.crypt("mypassword123!", fmt_and_salt)

        assert expected_value == shadow_users["tom"]

    def test_shadow_expected_users(self, class_client):
        """Test that the right set of users is in /etc/shadow."""
        shadow = class_client.read_from_file("/etc/shadow")
        for user_dict in USERS_DICTS:
            if "name" in user_dict:
                assert "{}:".format(user_dict["name"]) in shadow

    def test_sshd_config(self, class_client):
        """Test that SSH password auth is enabled."""
        sshd_config = class_client.read_from_file("/etc/ssh/sshd_config")
        # We look for the exact line match, to avoid a commented line matching
        assert "PasswordAuthentication yes" in sshd_config.splitlines()


@pytest.mark.ci
@pytest.mark.user_data(LIST_USER_DATA)
class TestPasswordList(Mixin):
    """Launch an instance with LIST_USER_DATA, ensure Mixin tests pass."""


@pytest.mark.ci
@pytest.mark.user_data(STRING_USER_DATA)
class TestPasswordListString(Mixin):
    """Launch an instance with STRING_USER_DATA, ensure Mixin tests pass."""
