"""These tests are for code in the cloudinit.user_data module.

These are NOT general tests for user data processing.
"""

import email
from email.mime.base import MIMEBase

import pytest

from cloudinit import subp, user_data
from tests.unittests.util import gzip_text


def count_messages(root):
    return sum(not user_data.is_skippable(m) for m in root.walk())


class TestMessageFromString:
    def test_unicode_not_messed_up(self):
        roundtripped = email.message_from_string("\n").as_string()
        assert "\x00" not in roundtripped


class TestUDProcess:
    @pytest.mark.parametrize(
        "msg",
        [
            pytest.param("#cloud-config\napt_update: True\n", id="str"),
            pytest.param(b"#cloud-config\napt_update: True\n", id="bytes"),
            pytest.param(
                gzip_text("#cloud-config\napt_update: True\n"),
                id="compressed",
            ),
        ],
    )
    def test_type_in_userdata(self, msg):
        ud_proc = user_data.UserDataProcessor({})
        message = ud_proc.process(msg)
        assert count_messages(message)


class TestConvertString:
    @pytest.mark.parametrize(
        "blob,decode",
        [
            pytest.param("hi mom", False, id="str"),
            pytest.param(b"#!/bin/bash\necho \xc3\x84\n", True, id="bytes"),
            pytest.param(b"\x32\x32", True, id="binary"),
        ],
    )
    def test_mime_conversion_preserves_content(self, blob, decode):
        """Ensure for each type of input, the content is preserved."""
        assert (
            user_data.convert_string(blob).get_payload(decode=decode) == blob
        )

    def test_handle_mime_parts(self):
        """Mime parts are properly returned as a mime message."""
        message = MIMEBase("text", "plain")
        message.set_payload("Just text")
        msg = user_data.convert_string(str(message))
        assert "Just text" == msg.get_payload(decode=False)


GOOD_MESSAGE = """\
-----BEGIN PGP MESSAGE-----

Pass:AMockWillDecryptMeIntoACloudConfig
-----END PGP MESSAGE-----
"""

CLOUD_CONFIG = """\
#cloud-config
password: password
"""

BAD_MESSAGE = """\
-----BEGIN PGP MESSAGE-----

Fail:AMockWillFailToDecryptMe
-----END PGP MESSAGE-----
"""


def my_subp(*args, **kwargs):
    if args[0][0] == "gpg":
        if "Pass:" in kwargs["data"]:
            return subp.SubpResult(CLOUD_CONFIG, "gpg: Good signature")
        elif "Fail:" in kwargs["data"]:
            raise subp.ProcessExecutionError(
                "", "gpg: public key decryption failed", 2, args[0]
            )
    return subp.SubpResult("", "")


class TestPgpData:
    def test_pgp_decryption(self, mocker):
        mocker.patch("cloudinit.subp.subp", side_effect=my_subp)
        ud_proc = user_data.UserDataProcessor({})
        message = ud_proc.process(GOOD_MESSAGE)
        parts = [p for p in message.walk() if not user_data.is_skippable(p)]
        assert len(parts) == 1
        part = parts[0]
        assert part.get_payload() == CLOUD_CONFIG

    def test_pgp_decryption_failure(self, mocker):
        mocker.patch("cloudinit.subp.subp", side_effect=my_subp)
        ud_proc = user_data.UserDataProcessor({})
        with pytest.raises(
            RuntimeError, match="Failed decrypting user data payload"
        ):
            ud_proc.process(BAD_MESSAGE)

    def test_pgp_required(self, mocker):
        mocker.patch("cloudinit.subp.subp", side_effect=my_subp)
        ud_proc = user_data.UserDataProcessor({})
        message = ud_proc.process(GOOD_MESSAGE, require_signature=True)
        parts = [p for p in message.walk() if not user_data.is_skippable(p)]
        assert len(parts) == 1
        part = parts[0]
        assert part.get_payload() == CLOUD_CONFIG

    def test_pgp_required_with_no_pgp_message(self, mocker):
        mocker.patch("cloudinit.subp.subp", side_effect=my_subp)
        ud_proc = user_data.UserDataProcessor({})
        with pytest.raises(RuntimeError, match="content is not signed"):
            ud_proc.process(CLOUD_CONFIG, require_signature=True)

    def test_pgp_in_list_disallowed(self, mocker):
        mocker.patch("cloudinit.subp.subp", side_effect=my_subp)
        ud_proc = user_data.UserDataProcessor({})
        with pytest.raises(
            RuntimeError,
            match="PGP message must encompass entire user data or vendor data",
        ):
            ud_proc.process([GOOD_MESSAGE, GOOD_MESSAGE])
