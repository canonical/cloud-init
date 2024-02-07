# This file is part of cloud-init. See LICENSE file for license information.

import os
import stat
from functools import partial
from textwrap import dedent
from typing import NamedTuple
from unittest import mock
from unittest.mock import patch

import pytest

from cloudinit import ssh_util, util

M_PATH = "cloudinit.ssh_util."


class FakePwEnt(NamedTuple):
    pw_name: str = "UNSET_pw_name"
    pw_passwd: str = "UNSET_w_passwd"
    pw_uid: str = "UNSET_pw_uid"
    pw_gid: str = "UNSET_pw_gid"
    pw_gecos: str = "UNSET_pw_gecos"
    pw_dir: str = "UNSET_pw_dir"
    pw_shell: str = "UNSET_pw_shell"


def mock_get_owner(updated_permissions, value):
    try:
        return updated_permissions[value][0]
    except ValueError:
        return util.get_owner(value)


def mock_get_group(updated_permissions, value):
    try:
        return updated_permissions[value][1]
    except ValueError:
        return util.get_group(value)


def mock_get_user_groups(username):
    return username


def mock_get_permissions(updated_permissions, value):
    try:
        return updated_permissions[value][2]
    except ValueError:
        return util.get_permissions(value)


def mock_getpwnam(users, username):
    return users[username]


# Do not use these public keys, most of them are fetched from
# the testdata for OpenSSH, and their private keys are available
# https://github.com/openssh/openssh-portable/tree/master/regress/unittests/sshkey/testdata
VALID_CONTENT = {
    "ecdsa": (
        "AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBITrGBB3cgJ"
        "J7fPxvtMW9H3oRisNpJ3OAslxZeyP7I0A9BPAW0RQIwHVtVnM7zrp4nI+JLZov/"
        "Ql7lc2leWL7CY="
    ),
    "rsa": (
        "AAAAB3NzaC1yc2EAAAABIwAAAQEA3I7VUf2l5gSn5uavROsc5HRDpZdQueUq5oz"
        "emNSj8T7enqKHOEaFoU2VoPgGEWC9RyzSQVeyD6s7APMcE82EtmW4skVEgEGSbD"
        "c1pvxzxtchBj78hJP6Cf5TCMFSXw+Fz5rF1dR23QDbN1mkHs7adr8GW4kSWqU7Q"
        "7NDwfIrJJtO7Hi42GyXtvEONHbiRPOe8stqUly7MvUoN+5kfjBM8Qqpfl2+FNhT"
        "YWpMfYdPUnE7u536WqzFmsaqJctz3gBxH9Ex7dFtrxR4qiqEr9Qtlu3xGn7Bw07"
        "/+i1D+ey3ONkZLN+LQ714cgj8fRS4Hj29SCmXp5Kt5/82cD/VN3NtHw=="
    ),
    "ed25519": (
        "AAAAC3NzaC1lZDI1NTE5AAAAIA1J77+CrJ8p6/vWCEzuylqJNMHUP/XmeYyGVWb8lnDd"
    ),
    "ecdsa-sha2-nistp256-cert-v01@openssh.com": (
        "AAAAKGVjZHNhLXNoYTItbmlzdHAyNTYtY2VydC12MDFAb3BlbnNzaC5jb20AAAA"
        "gQIfwT/+UX68/hlKsdKuaOuAVB6ftTg03SlP/uH4OBEwAAAAIbmlzdHAyNTYAAA"
        "BBBEjA0gjJmPM6La3sXyfNlnjilvvGY6I2M8SvJj4o3X/46wcUbPWTaj4RF3EXw"
        "HvNxplYBwdPlk2zEecvf9Cs2BMAAAAAAAAAAAAAAAEAAAAYa2V5cy9lY2RzYS1z"
        "aGEyLW5pc3RwMjU2AAAAAAAAAAAAAAAA//////////8AAAAAAAAAggAAABVwZXJ"
        "taXQtWDExLWZvcndhcmRpbmcAAAAAAAAAF3Blcm1pdC1hZ2VudC1mb3J3YXJkaW"
        "5nAAAAAAAAABZwZXJtaXQtcG9ydC1mb3J3YXJkaW5nAAAAAAAAAApwZXJtaXQtc"
        "HR5AAAAAAAAAA5wZXJtaXQtdXNlci1yYwAAAAAAAAAAAAAAaAAAABNlY2RzYS1z"
        "aGEyLW5pc3RwMjU2AAAACG5pc3RwMjU2AAAAQQRH6Y9Q1+ocQ8ETKW3LjQqtxg7"
        "OuSSDacxmmQatQVaIawwjCbmntyEAqmVj3v9ElDSXnO5m7TyYMBQu4+vsh76RAA"
        "AAZQAAABNlY2RzYS1zaGEyLW5pc3RwMjU2AAAASgAAACEA47Cl2MMhr+glPGuxx"
        "2tM3QXkDcwdP0SxSEW5yy4XV5oAAAAhANNMm1cdVlAt3hmycQgdD82zPlg5YvVO"
        "iN0SQTbgVD8i"
    ),
    "ecdsa-sha2-nistp256": (
        "AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEjA0gjJmPM"
        "6La3sXyfNlnjilvvGY6I2M8SvJj4o3X/46wcUbPWTaj4RF3EXwHvNxplYBwdPlk"
        "2zEecvf9Cs2BM="
    ),
    "ecdsa-sha2-nistp384-cert-v01@openssh.com": (
        "AAAAKGVjZHNhLXNoYTItbmlzdHAzODQtY2VydC12MDFAb3BlbnNzaC5jb20AAAA"
        "grnSvDsK1EnCZndO1IyGWcGkVgVSkPWi/XO2ybPFyLVUAAAAIbmlzdHAzODQAAA"
        "BhBAaYSQs+8TT0Tzciy0dorwhur6yzOGUrYQ6ueUQYWbE7eNdHmhsVrlpGPgSaY"
        "ByhXtAJiPOMqLU5h0eb3sCtM3ek4NvjXFTGTqPrrxJI6q0OsgrtkGE7UM9ZsfMm"
        "7q6BOAAAAAAAAAAAAAAAAQAAABhrZXlzL2VjZHNhLXNoYTItbmlzdHAzODQAAAA"
        "AAAAAAAAAAAD//////////wAAAAAAAACCAAAAFXBlcm1pdC1YMTEtZm9yd2FyZG"
        "luZwAAAAAAAAAXcGVybWl0LWFnZW50LWZvcndhcmRpbmcAAAAAAAAAFnBlcm1pd"
        "C1wb3J0LWZvcndhcmRpbmcAAAAAAAAACnBlcm1pdC1wdHkAAAAAAAAADnBlcm1p"
        "dC11c2VyLXJjAAAAAAAAAAAAAACIAAAAE2VjZHNhLXNoYTItbmlzdHAzODQAAAA"
        "IbmlzdHAzODQAAABhBLWbubcMzcWc7lMTCMGVXZlaVvUOHLjpr6SOOScFFrd8K9"
        "Gl8nYELST5HZ1gym65m+MG6/tbrUWIY/flLWNIe+WtqxrdPPGdIhFruCwNw2peZ"
        "SbQOa/o3AGnJ/vO6EKEGAAAAIQAAAATZWNkc2Etc2hhMi1uaXN0cDM4NAAAAGkA"
        "AAAxAL10JHd5bvnbpD+fet/k1YE1BEIrqGXaoIIJ9ReE5H4nTK1uQJzMD7+wwGK"
        "RVYqYQgAAADAiit0UCMDAUbjD+R2x4LvU3x/t8G3sdqDLRNfMRpjZpvcS8AwC+Y"
        "VFVSQNn0AyzW0="
    ),
    "ecdsa-sha2-nistp384": (
        "AAAAE2VjZHNhLXNoYTItbmlzdHAzODQAAAAIbmlzdHAzODQAAABhBAaYSQs+8TT"
        "0Tzciy0dorwhur6yzOGUrYQ6ueUQYWbE7eNdHmhsVrlpGPgSaYByhXtAJiPOMqL"
        "U5h0eb3sCtM3ek4NvjXFTGTqPrrxJI6q0OsgrtkGE7UM9ZsfMm7q6BOA=="
    ),
    "ecdsa-sha2-nistp521-cert-v01@openssh.com": (
        "AAAAKGVjZHNhLXNoYTItbmlzdHA1MjEtY2VydC12MDFAb3BlbnNzaC5jb20AAAA"
        "gGmRzkkMvRFk1V5U3m3mQ2nfW20SJVXk1NKnT5iZGDcEAAAAIbmlzdHA1MjEAAA"
        "CFBAHosAOHAI1ZkerbKYQ72S6uit1u77PCj/OalZtXgsxv0TTAZB273puG2X94C"
        "Q8yyNHcby87zFZHdv5BSKyZ/cyREAAeiAcSakop9VS3+bUfZpEIqwBZXarwUjnR"
        "nxprkcQ0rfCCdagkGZr/OA7DemK2D8tKLTHsKoEEWNImo6/pXDkFxAAAAAAAAAA"
        "AAAAAAQAAABhrZXlzL2VjZHNhLXNoYTItbmlzdHA1MjEAAAAAAAAAAAAAAAD///"
        "///////wAAAAAAAACCAAAAFXBlcm1pdC1YMTEtZm9yd2FyZGluZwAAAAAAAAAXc"
        "GVybWl0LWFnZW50LWZvcndhcmRpbmcAAAAAAAAAFnBlcm1pdC1wb3J0LWZvcndh"
        "cmRpbmcAAAAAAAAACnBlcm1pdC1wdHkAAAAAAAAADnBlcm1pdC11c2VyLXJjAAA"
        "AAAAAAAAAAACsAAAAE2VjZHNhLXNoYTItbmlzdHA1MjEAAAAIbmlzdHA1MjEAAA"
        "CFBAC6hFVXM1XEg/7qKkp5sLZuANGQVW88b5pPn2ZcK0td9IQstLH6BwWuZ6MPE"
        "ogiDlvx9HD1BaKGBBfkxgOY8NGFzQHbjU9eTWH3gt0RATDbZsij1pSkFPnAXdU9"
        "SjfogYloI2xdHaTCgWp3zgsUV+BBQ0QGGv2MqqcOmrF0f5YEJeOffAAAAKcAAAA"
        "TZWNkc2Etc2hhMi1uaXN0cDUyMQAAAIwAAABCAT+vSOYPuYVTDopDW08576d5Sb"
        "edXQMOu1op4CQIm98VKtAXvu5dfioi5VYAqpte8M+UxEMOMiQWJp+U9exYf6LuA"
        "AAAQgEzkIpX3yKXPaPcK17mNx40ujEDitm4ARmbhAge0sFhZtf7YIgI55b6vkI8"
        "JvMJkzQCBF1cpNOaIpVh1nFZNBphMQ=="
    ),
    "ecdsa-sha2-nistp521": (
        "AAAAE2VjZHNhLXNoYTItbmlzdHA1MjEAAAAIbmlzdHA1MjEAAACFBAHosAOHAI1"
        "ZkerbKYQ72S6uit1u77PCj/OalZtXgsxv0TTAZB273puG2X94CQ8yyNHcby87zF"
        "ZHdv5BSKyZ/cyREAAeiAcSakop9VS3+bUfZpEIqwBZXarwUjnRnxprkcQ0rfCCd"
        "agkGZr/OA7DemK2D8tKLTHsKoEEWNImo6/pXDkFxA=="
    ),
    "sk-ecdsa-sha2-nistp256-cert-v01@openssh.com": (
        "AAAAIHNzaC1lZDI1NTE5LWNlcnQtdjAxQG9wZW5zc2guY29tAAAAIIxzuxl4z3u"
        "wAIslne8Huft+1n1IhHAlNbWZkQyyECCGAAAAIFOG6kY7Rf4UtCFvPwKgo/BztX"
        "ck2xC4a2WyA34XtIwZAAAAAAAAAAgAAAACAAAABmp1bGl1cwAAABIAAAAFaG9zd"
        "DEAAAAFaG9zdDIAAAAANowB8AAAAABNHmBwAAAAAAAAAAAAAAAAAAAAMwAAAAtz"
        "c2gtZWQyNTUxOQAAACBThupGO0X+FLQhbz8CoKPwc7V3JNsQuGtlsgN+F7SMGQA"
        "AAFMAAAALc3NoLWVkMjU1MTkAAABABGTn+Bmz86Ajk+iqKCSdP5NClsYzn4alJd"
        "0V5bizhP0Kumc/HbqQfSt684J1WdSzih+EjvnTgBhK9jTBKb90AQ=="
    ),
    "sk-ecdsa-sha2-nistp256@openssh.com": (
        "AAAAInNrLWVjZHNhLXNoYTItbmlzdHAyNTZAb3BlbnNzaC5jb20AAAAIbmlzdHA"
        "yNTYAAABBBIELQJ2DgvaX1yQlKFokfWM2suuaCFI2qp0eJodHyg6O4ifxc3XpRK"
        "d1OS8dNYQtE/YjdXSrA+AOnMF5ns2Nkx4AAAAEc3NoOg=="
    ),
    "sk-ssh-ed25519-cert-v01@openssh.com": (
        "AAAAIHNzaC1lZDI1NTE5LWNlcnQtdjAxQG9wZW5zc2guY29tAAAAIIxzuxl4z3u"
        "wAIslne8Huft+1n1IhHAlNbWZkQyyECCGAAAAIFOG6kY7Rf4UtCFvPwKgo/BztX"
        "ck2xC4a2WyA34XtIwZAAAAAAAAAAgAAAACAAAABmp1bGl1cwAAABIAAAAFaG9zd"
        "DEAAAAFaG9zdDIAAAAANowB8AAAAABNHmBwAAAAAAAAAAAAAAAAAAAAMwAAAAtz"
        "c2gtZWQyNTUxOQAAACBThupGO0X+FLQhbz8CoKPwc7V3JNsQuGtlsgN+F7SMGQA"
        "AAFMAAAALc3NoLWVkMjU1MTkAAABABGTn+Bmz86Ajk+iqKCSdP5NClsYzn4alJd"
        "0V5bizhP0Kumc/HbqQfSt684J1WdSzih+EjvnTgBhK9jTBKb90AQ=="
    ),
    "sk-ssh-ed25519@openssh.com": (
        "AAAAGnNrLXNzaC1lZDI1NTE5QG9wZW5zc2guY29tAAAAICFo/k5LU8863u66YC9"
        "eUO2170QduohPURkQnbLa/dczAAAABHNzaDo="
    ),
    "ssh-ed25519-cert-v01@openssh.com": (
        "AAAAIHNzaC1lZDI1NTE5LWNlcnQtdjAxQG9wZW5zc2guY29tAAAAIIxzuxl4z3u"
        "wAIslne8Huft+1n1IhHAlNbWZkQyyECCGAAAAIFOG6kY7Rf4UtCFvPwKgo/BztX"
        "ck2xC4a2WyA34XtIwZAAAAAAAAAAgAAAACAAAABmp1bGl1cwAAABIAAAAFaG9zd"
        "DEAAAAFaG9zdDIAAAAANowB8AAAAABNHmBwAAAAAAAAAAAAAAAAAAAAMwAAAAtz"
        "c2gtZWQyNTUxOQAAACBThupGO0X+FLQhbz8CoKPwc7V3JNsQuGtlsgN+F7SMGQA"
        "AAFMAAAALc3NoLWVkMjU1MTkAAABABGTn+Bmz86Ajk+iqKCSdP5NClsYzn4alJd"
        "0V5bizhP0Kumc/HbqQfSt684J1WdSzih+EjvnTgBhK9jTBKb90AQ=="
    ),
    "ssh-ed25519": (
        "AAAAC3NzaC1lZDI1NTE5AAAAIFOG6kY7Rf4UtCFvPwKgo/BztXck2xC4a2WyA34XtIwZ"
    ),
    "ssh-rsa-cert-v01@openssh.com": (
        "AAAAHHNzaC1yc2EtY2VydC12MDFAb3BlbnNzaC5jb20AAAAg98LhS2EHxLOWCLo"
        "pZPwHdg/RJXusnkOqQXSc9R7aITkAAAADAQABAAAAgQDLV5lUTt7FrADseB/CGh"
        "EZzpoojjEW5y8+ePvLppmK3MmMI18ud6vxzpK3bwZLYkVSyfJYI0HmIuGhdu7yM"
        "rW6wb84gbq8C31Xoe9EORcIUuGSvDKdNSM1SjlhDquRblDFB8kToqXyx1lqrXec"
        "XylxIUOL0jE+u0rU1967pDJx+wAAAAAAAAAFAAAAAgAAAAZqdWxpdXMAAAASAAA"
        "ABWhvc3QxAAAABWhvc3QyAAAAADaMAfAAAAAATR5gcAAAAAAAAAAAAAAAAAAAAD"
        "MAAAALc3NoLWVkMjU1MTkAAAAgU4bqRjtF/hS0IW8/AqCj8HO1dyTbELhrZbIDf"
        "he0jBkAAABTAAAAC3NzaC1lZDI1NTE5AAAAQI3QGlUCzC07KorupxpDkkGy6tni"
        "aZ8EvBflzvv+itXWNchGvfUeHmVT6aX0sRqehdz/lR+GmXRoZBhofwh0qAM="
    ),
    "ssh-rsa": (
        "AAAAB3NzaC1yc2EAAAADAQABAAAAgQDLV5lUTt7FrADseB/CGhEZzpoojjEW5y8"
        "+ePvLppmK3MmMI18ud6vxzpK3bwZLYkVSyfJYI0HmIuGhdu7yMrW6wb84gbq8C3"
        "1Xoe9EORcIUuGSvDKdNSM1SjlhDquRblDFB8kToqXyx1lqrXecXylxIUOL0jE+u"
        "0rU1967pDJx+w=="
    ),
    "ssh-xmss-cert-v01@openssh.com": (
        "AAAAHXNzaC14bXNzLWNlcnQtdjAxQG9wZW5zc2guY29tAAAAIM2UD0IH+Igsekq"
        "xjTO5f36exX4WGRMCtDGPjwfbXblxAAAAFVhNU1NfU0hBMi0yNTZfVzE2X0gxMA"
        "AAAEDI83/K5JMOy0BMJgQypRdz35ApAnoQinMJ8ZMoZPaEJF8Z4rANQlfzaAXum"
        "N3RDU5CGIUGGw+WJ904G/wwEq9CAAAAAAAAAAAAAAABAAAACWtleXMveG1zcwAA"
        "AAAAAAAAAAAAAP//////////AAAAAAAAAIIAAAAVcGVybWl0LVgxMS1mb3J3YXJ"
        "kaW5nAAAAAAAAABdwZXJtaXQtYWdlbnQtZm9yd2FyZGluZwAAAAAAAAAWcGVybW"
        "l0LXBvcnQtZm9yd2FyZGluZwAAAAAAAAAKcGVybWl0LXB0eQAAAAAAAAAOcGVyb"
        "Wl0LXVzZXItcmMAAAAAAAAAAAAAAHUAAAAUc3NoLXhtc3NAb3BlbnNzaC5jb20A"
        "AAAVWE1TU19TSEEyLTI1Nl9XMTZfSDEwAAAAQA+irIyT2kaOd07YWZT/QItzNBZ"
        "kUYwnqZJihQ7BxuyiDP4HEFbnfYnnIZXx9Asyi7vDyZRvi+AMSOzmMSq4JnkAAA"
        "ngAAAAFHNzaC14bXNzQG9wZW5zc2guY29tAAAJxAAAAAAFjaKTDc+7Hu2uFGIab"
        "3NAku8HbbGtrq/uGXOxmqxu4RaLqmwofl5iXk3nMwWEhQAb99vAc9D9ZFtfxJO4"
        "STYUTjbj4BxToov/uvbYfE5VeO6sMvkGglgh9YHkCTAItsG8EmGT1SIPfKYzLlN"
        "jvUlbcv0PaPFMJ0wzS9mNfuRf+KUhf3dxQ6zaMrBH3KEJ8Me2kNjhnh6rNPROeI"
        "N+IcStSKsydYuiySGKS/orsH38XysuK5QqLizbHJY3cqLbkW9LsIijb+pfEJh4Y"
        "bOoAbraWAv9ySnWCyRhvw2x8uJ0ZM+p5WSRiZfB3JxCpOhHgiKa9TdmdjnAtnED"
        "zqKOj/gM7y9mesn5ydQI0bENOGymlw0ThUGKbXMxn87Hc9dDPURUBmoO3NGjPDf"
        "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"
        "Jy3QalZbaoWtcyyvXxR2sqhVR9F7Cmasq4="
    ),
    "ssh-xmss@openssh.com": (
        "AAAAFHNzaC14bXNzQG9wZW5zc2guY29tAAAAFVhNU1NfU0hBMi0yNTZfVzE2X0g"
        "xMAAAAECqptWnK94d+Sj2xcdTu8gz+75lawZoLSZFqC5IhbYuT/Z3oBZCim6yt+"
        "HAmk6MKldl3Fg+74v4sR/SII0I0Jv/"
    ),
}

KEY_TYPES = list(VALID_CONTENT.keys())

TEST_OPTIONS = (
    "no-port-forwarding,no-agent-forwarding,no-X11-forwarding,"
    'command="echo \'Please login as the user "ubuntu" rather than the'
    'user "root".\';echo;sleep 10"'
)


class TestAuthKeyLineParser:
    @pytest.mark.parametrize("with_options", [True, False])
    @pytest.mark.parametrize("with_comment", [True, False])
    @pytest.mark.parametrize("ktype", KEY_TYPES)
    def test_parse(self, ktype, with_comment, with_options):
        content = VALID_CONTENT[ktype]
        comment = "user-%s@host" % ktype
        options = TEST_OPTIONS

        line_args = []
        if with_options:
            line_args.append(options)
        line_args.extend(
            [
                ktype,
                content,
            ]
        )
        if with_comment:
            line_args.append(comment)
        line = " ".join(line_args)

        key = ssh_util.AuthKeyLineParser().parse(line)

        assert key.base64 == content
        assert key.keytype == ktype
        if with_options:
            assert key.options == options
        else:
            assert key.options is None
        if with_comment:
            assert key.comment == comment
        else:
            assert key.comment == ""

    def test_parse_with_options_passed_in(self):
        # test key line with key type and base64 only
        parser = ssh_util.AuthKeyLineParser()

        baseline = " ".join(("rsa", VALID_CONTENT["rsa"], "user@host"))
        myopts = "no-port-forwarding,no-agent-forwarding"

        key = parser.parse("allowedopt" + " " + baseline)
        assert key.options == "allowedopt"

        key = parser.parse("overridden_opt " + baseline, options=myopts)
        assert key.options == myopts

    def test_parse_invalid_keytype(self):
        parser = ssh_util.AuthKeyLineParser()
        key = parser.parse(" ".join(["badkeytype", VALID_CONTENT["rsa"]]))

        assert not key.valid()


class TestUpdateAuthorizedKeys:
    @pytest.mark.parametrize(
        "new_entries",
        [
            (
                [
                    " ".join(("rsa", VALID_CONTENT["rsa"], "new_comment1")),
                ]
            ),
            pytest.param(
                [
                    " ".join(("rsa", VALID_CONTENT["rsa"], "new_comment1")),
                    "xxx-invalid-thing1",
                    "xxx-invalid-blob2",
                ],
                id="skip-invalid-entries",
            ),
        ],
    )
    def test_new_keys_replace(self, new_entries):
        """new entries with the same base64 should replace old."""
        orig_entries = [
            " ".join(("rsa", VALID_CONTENT["rsa"], "orig_comment1")),
            " ".join(("ecdsa", VALID_CONTENT["ecdsa"], "orig_comment2")),
        ]

        expected = "\n".join([new_entries[0], orig_entries[1]]) + "\n"

        parser = ssh_util.AuthKeyLineParser()
        found = ssh_util.update_authorized_keys(
            [parser.parse(p) for p in orig_entries],
            [parser.parse(p) for p in new_entries],
        )

        assert expected == found


@mock.patch(M_PATH + "util.load_text_file")
@mock.patch(M_PATH + "os.path.isfile")
class TestParseSSHConfig:
    @pytest.mark.parametrize(
        "is_file, file_content",
        [
            pytest.param(True, ("",), id="empty-file"),
            pytest.param(False, IOError, id="not-a-file"),
        ],
    )
    def test_dummy_file(self, m_is_file, m_load_file, is_file, file_content):
        m_is_file.return_value = is_file
        m_load_file.side_effect = file_content
        ret = ssh_util.parse_ssh_config("notmatter")
        assert [] == ret

    @pytest.mark.parametrize(
        "file_content",
        [
            pytest.param(["# This is a comment"], id="comment_line"),
            pytest.param(
                ["# This is a comment", "# This is another comment"],
                id="two-comment_lines",
            ),
        ],
    )
    def test_comment_line(self, m_is_file, m_load_file, file_content):
        m_is_file.return_value = True
        m_load_file.return_value = "\n".join(file_content)
        ret = ssh_util.parse_ssh_config("some real file")
        assert len(file_content) == len(ret)
        assert file_content[0] == ret[0].line

    def test_blank_lines(self, m_is_file, m_load_file):
        m_is_file.return_value = True
        lines = ["", "\t", " "]
        m_load_file.return_value = "\n".join(lines)
        ret = ssh_util.parse_ssh_config("some real file")
        assert len(lines) == len(ret)
        for line in ret:
            assert "" == line.line

    @pytest.mark.parametrize(
        "file_content, expected_key, expected_value",
        [
            pytest.param("foo bar", "foo", "bar", id="lower-case"),
            pytest.param("Foo Bar", "foo", "Bar", id="upper-case"),
            pytest.param("foo=bar", "foo", "bar", id="lower-case-with-equals"),
            pytest.param("Foo=bar", "foo", "bar", id="upper-case-with-equals"),
        ],
    )
    def test_case_config(
        self,
        m_is_file,
        m_load_file,
        file_content,
        expected_key,
        expected_value,
    ):
        m_is_file.return_value = True
        m_load_file.return_value = file_content
        ret = ssh_util.parse_ssh_config("some real file")
        assert 1 == len(ret)
        assert expected_key == ret[0].key
        assert expected_value == ret[0].value

    def test_duplicated_keys(self, m_is_file, m_load_file):
        file_content = [
            "HostCertificate /data/ssh/ssh_host_rsa_cert",
            "HostCertificate /data/ssh/ssh_host_ed25519_cert",
        ]
        m_is_file.return_value = True
        m_load_file.return_value = "\n".join(file_content)
        ret = ssh_util.parse_ssh_config("some real file")
        assert len(file_content) == len(ret)
        for i in range(len(file_content)):
            assert file_content[i] == ret[i].line


class TestUpdateSshConfigLines:
    """Test the update_ssh_config_lines method."""

    exlines = [
        "#PasswordAuthentication yes",
        "UsePAM yes",
        "# Comment line",
        "AcceptEnv LANG LC_*",
        "X11Forwarding no",
    ]
    pwauth = "PasswordAuthentication"

    def check_line(self, line, opt, val):
        assert line.key == opt.lower()
        assert line.value == val
        assert opt in str(line)
        assert val in str(line)

    @pytest.mark.parametrize(
        "key, value",
        [
            pytest.param("MyKey", "MyVal", id="new_option_added"),
            pytest.param(
                pwauth, "no", id="commented_out_not_updated_but_appended"
            ),
        ],
    )
    def test_update_ssh_config_lines(self, key, value):
        lines = ssh_util.parse_ssh_config_lines(list(self.exlines))
        result = ssh_util.update_ssh_config_lines(lines, {key: value})
        assert [key] == result
        self.check_line(lines[-1], key, value)

    def test_option_without_value(self):
        """Implementation only accepts key-value pairs."""
        extended_exlines = self.exlines.copy()
        denyusers_opt = "DenyUsers"
        extended_exlines.append(denyusers_opt)
        lines = ssh_util.parse_ssh_config_lines(list(extended_exlines))
        assert denyusers_opt not in str(lines)

    def test_single_option_updated(self):
        """A single update should have change made and line updated."""
        opt, val = ("UsePAM", "no")
        lines = ssh_util.parse_ssh_config_lines(list(self.exlines))
        result = ssh_util.update_ssh_config_lines(lines, {opt: val})
        assert [opt] == result
        self.check_line(lines[1], opt, val)

    def test_multiple_updates_with_add(self):
        """Verify multiple updates some added some changed, some not."""
        updates = {
            "UsePAM": "no",
            "X11Forwarding": "no",
            "NewOpt": "newval",
            "AcceptEnv": "LANG ADD LC_*",
        }
        lines = ssh_util.parse_ssh_config_lines(list(self.exlines))
        result = ssh_util.update_ssh_config_lines(lines, updates)
        assert set(["UsePAM", "NewOpt", "AcceptEnv"]) == set(result)
        self.check_line(lines[3], "AcceptEnv", updates["AcceptEnv"])

    def test_return_empty_if_no_changes(self):
        """If there are no changes, then return should be empty list."""
        updates = {"UsePAM": "yes"}
        lines = ssh_util.parse_ssh_config_lines(list(self.exlines))
        result = ssh_util.update_ssh_config_lines(lines, updates)
        assert [] == result
        assert self.exlines == [str(line) for line in lines]

    def test_keycase_not_modified(self):
        """Original case of key should not be changed on update.
        This behavior is to keep original config as much intact as can be."""
        updates = {"usepam": "no"}
        lines = ssh_util.parse_ssh_config_lines(list(self.exlines))
        result = ssh_util.update_ssh_config_lines(lines, updates)
        assert ["usepam"] == result
        assert "UsePAM no" == str(lines[1])


class TestUpdateSshConfig:
    cfgdata = "\n".join(["#Option val", "MyKey ORIG_VAL", ""])

    def test_modified(self, tmpdir):
        mycfg = tmpdir.join("ssh_config_1")
        util.write_file(mycfg, self.cfgdata)
        ret = ssh_util.update_ssh_config({"MyKey": "NEW_VAL"}, mycfg)
        assert True is ret
        found = util.load_text_file(mycfg)
        assert self.cfgdata.replace("ORIG_VAL", "NEW_VAL") == found
        # assert there is a newline at end of file (LP: #1677205)
        assert "\n" == found[-1]

    def test_not_modified(self, tmpdir):
        mycfg = tmpdir.join("ssh_config_2")
        util.write_file(mycfg, self.cfgdata)
        with patch("cloudinit.ssh_util.util.write_file") as m_write_file:
            ret = ssh_util.update_ssh_config({"MyKey": "ORIG_VAL"}, mycfg)
        assert False is ret
        assert self.cfgdata == util.load_text_file(mycfg)
        m_write_file.assert_not_called()

    def test_without_include(self, tmpdir):
        mycfg = tmpdir.join("sshd_config")
        cfg = "X Y"
        util.write_file(mycfg, cfg)
        assert ssh_util.update_ssh_config({"key": "value"}, mycfg)
        assert "X Y\nkey value\n" == util.load_text_file(mycfg)
        expected_conf_file = f"{mycfg}.d/50-cloud-init.conf"
        assert not os.path.isfile(expected_conf_file)

    @pytest.mark.parametrize(
        "cfg",
        ["Include {mycfg}.d/*.conf", "Include {mycfg}.d/*.conf # comment"],
    )
    def test_with_include(self, cfg, tmpdir):
        mycfg = tmpdir.join("sshd_config")
        util.write_file(mycfg, cfg.format(mycfg=mycfg))
        assert ssh_util.update_ssh_config({"key": "value"}, mycfg)
        expected_conf_file = f"{mycfg}.d/50-cloud-init.conf"
        assert os.path.isfile(expected_conf_file)
        assert 0o600 == stat.S_IMODE(os.stat(expected_conf_file).st_mode)
        assert "key value\n" == util.load_text_file(expected_conf_file)

    def test_with_commented_include(self, tmpdir):
        mycfg = tmpdir.join("sshd_config")
        cfg = f"# Include {mycfg}.d/*.conf"
        util.write_file(mycfg, cfg)
        assert ssh_util.update_ssh_config({"key": "value"}, mycfg)
        assert f"{cfg}\nkey value\n" == util.load_text_file(mycfg)
        expected_conf_file = f"{mycfg}.d/50-cloud-init.conf"
        assert not os.path.isfile(expected_conf_file)

    def test_with_other_include(self, tmpdir):
        mycfg = tmpdir.join("sshd_config")
        cfg = f"Include other_{mycfg}.d/*.conf"
        util.write_file(mycfg, cfg)
        assert ssh_util.update_ssh_config({"key": "value"}, mycfg)
        assert f"{cfg}\nkey value\n" == util.load_text_file(mycfg)
        expected_conf_file = f"{mycfg}.d/50-cloud-init.conf"
        assert not os.path.isfile(expected_conf_file)
        assert not os.path.isfile(f"other_{mycfg}.d/50-cloud-init.conf")


class TestAppendSshConfig:
    cfgdata = "\n".join(["#Option val", "MyKey ORIG_VAL", ""])

    @mock.patch(M_PATH + "_ensure_cloud_init_ssh_config_file")
    def test_append_ssh_config(self, m_ensure_cloud_init_config_file, tmpdir):
        mycfg = tmpdir.join("ssh_config")
        util.write_file(mycfg, self.cfgdata)
        m_ensure_cloud_init_config_file.return_value = str(mycfg)
        ssh_util.append_ssh_config(
            [("MyKey", "NEW_VAL"), ("MyKey", "NEW_VAL_2")], mycfg
        )
        found = util.load_text_file(mycfg)
        expected_cfg = dedent(
            """\
            #Option val
            MyKey ORIG_VAL
            MyKey NEW_VAL
            MyKey NEW_VAL_2
            """
        )
        assert expected_cfg == found
        # assert there is a newline at end of file (LP: #1677205)
        assert "\n" == found[-1]


class TestBasicAuthorizedKeyParse:
    @pytest.mark.parametrize(
        "value, homedir, username, expected_rendered",
        [
            pytest.param(
                "/opt/%u/keys",
                "/home/bobby",
                "bobby",
                ["/opt/bobby/keys"],
                id="user",
            ),
            pytest.param(
                "/opt/%u",
                "/home/bobby",
                "bobby",
                ["/opt/bobby"],
                id="user_file",
            ),
            pytest.param(
                "/opt/%u/%u",
                "/home/bobby",
                "bobby",
                ["/opt/bobby/bobby"],
                id="user_file_2",
            ),
            pytest.param(
                "/keys/path1 /keys/path2",
                "/home/bobby",
                "bobby",
                ["/keys/path1", "/keys/path2"],
                id="multiple",
            ),
            pytest.param(
                "/keys/path1 /keys/%u",
                "/home/bobby",
                "bobby",
                ["/keys/path1", "/keys/bobby"],
                id="multiple_2",
            ),
            pytest.param(
                ".secret/keys",
                "/home/bobby",
                "bobby",
                ["/home/bobby/.secret/keys"],
                id="relative",
            ),
            pytest.param(
                "%h/.keys",
                "/homedirs/bobby",
                "bobby",
                ["/homedirs/bobby/.keys"],
                id="home",
            ),
            pytest.param(
                "%h/.keys .secret/keys /keys/path1 /opt/%u/keys",
                "/homedirs/bobby",
                "bobby",
                [
                    "/homedirs/bobby/.keys",
                    "/homedirs/bobby/.secret/keys",
                    "/keys/path1",
                    "/opt/bobby/keys",
                ],
                id="all",
            ),
        ],
    )
    def test_render_authorizedkeysfile_paths(
        self, value, homedir, username, expected_rendered
    ):
        assert expected_rendered == ssh_util.render_authorizedkeysfile_paths(
            value, homedir, username
        )


class TestMultipleSshAuthorizedKeysFile:
    def create_fake_users(
        self,
        names,
        mock_permissions,
        m_get_group,
        m_get_owner,
        m_get_permissions,
        m_getpwnam,
        users,
        tmpdir,
    ):
        homes = []

        root = str(tmpdir.join("root"))
        fpw = FakePwEnt(pw_name="root", pw_dir=root)
        users["root"] = fpw

        for name in names:
            home = str(tmpdir.join("home", name))
            fpw = FakePwEnt(pw_name=name, pw_dir=home)
            users[name] = fpw
            homes.append(home)

        m_get_permissions.side_effect = partial(
            mock_get_permissions, mock_permissions
        )
        m_get_owner.side_effect = partial(mock_get_owner, mock_permissions)
        m_get_group.side_effect = partial(mock_get_group, mock_permissions)
        m_getpwnam.side_effect = partial(mock_getpwnam, users)
        return homes

    def create_user_authorized_file(self, home, filename, content_key, keys):
        user_ssh_folder = os.path.join(home, ".ssh")
        # /tmp/home/<user>/.ssh/authorized_keys = content_key
        authorized_keys = str(os.path.join(user_ssh_folder, filename))
        util.write_file(authorized_keys, VALID_CONTENT[content_key])
        keys[authorized_keys] = content_key
        return authorized_keys

    def create_global_authorized_file(
        self, filename, content_key, keys, tmpdir
    ):
        authorized_keys = str(tmpdir.join(filename))
        util.write_file(authorized_keys, VALID_CONTENT[content_key])
        keys[authorized_keys] = content_key
        return authorized_keys

    def create_sshd_config(self, authorized_keys_files, tmpdir):
        sshd_config = str(tmpdir.join("sshd_config"))
        util.write_file(
            sshd_config, "AuthorizedKeysFile " + authorized_keys_files
        )
        return sshd_config

    def execute_and_check(self, user, sshd_config, solution, keys):
        (auth_key_fn, auth_key_entries) = ssh_util.extract_authorized_keys(
            user, sshd_config
        )
        content = ssh_util.update_authorized_keys(auth_key_entries, [])

        assert auth_key_fn == solution
        for path, key in keys.items():
            if path == solution:
                assert VALID_CONTENT[key] in content
            else:
                assert VALID_CONTENT[key] not in content

    @pytest.mark.parametrize("inverted", [False, True])
    @patch("cloudinit.ssh_util.pwd.getpwnam")
    @patch("cloudinit.util.get_permissions")
    @patch("cloudinit.util.get_owner")
    @patch("cloudinit.util.get_group")
    def test_single_user_two_local_files(
        self,
        m_get_group,
        m_get_owner,
        m_get_permissions,
        m_getpwnam,
        inverted,
        tmpdir,
    ):
        user_bobby = "bobby"
        keys = {}
        users = {}
        mock_permissions = {
            tmpdir.join("home", "bobby"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh", "user_keys"): (
                "bobby",
                "bobby",
                0o600,
            ),
            tmpdir.join("home", "bobby", ".ssh", "authorized_keys"): (
                "bobby",
                "bobby",
                0o600,
            ),
        }

        homes = self.create_fake_users(
            [user_bobby],
            mock_permissions,
            m_get_group,
            m_get_owner,
            m_get_permissions,
            m_getpwnam,
            users,
            tmpdir,
        )
        home = homes[0]

        # /tmp/home/bobby/.ssh/authorized_keys = rsa
        authorized_keys = self.create_user_authorized_file(
            home, "authorized_keys", "rsa", keys
        )

        # /tmp/home/bobby/.ssh/user_keys = ed25519
        user_keys = self.create_user_authorized_file(
            home, "user_keys", "ed25519", keys
        )

        # /tmp/sshd_config
        if not inverted:
            options = f"{authorized_keys} {user_keys}"
        else:
            options = f"{user_keys} {authorized_keys}"
        sshd_config = self.create_sshd_config(options, tmpdir)

        if not inverted:
            exec_args = (user_bobby, sshd_config, authorized_keys, keys)
        else:
            exec_args = (user_bobby, sshd_config, user_keys, keys)

        self.execute_and_check(*exec_args)

    @pytest.mark.parametrize("inverted", [False, True])
    @patch("cloudinit.ssh_util.pwd.getpwnam")
    @patch("cloudinit.util.get_permissions")
    @patch("cloudinit.util.get_owner")
    @patch("cloudinit.util.get_group")
    def test_single_user_local_global_files(
        self,
        m_get_group,
        m_get_owner,
        m_get_permissions,
        m_getpwnam,
        inverted,
        tmpdir,
    ):
        user_bobby = "bobby"
        keys = {}
        users = {}
        mock_permissions = {
            tmpdir.join("home", "bobby"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh", "user_keys"): (
                "bobby",
                "bobby",
                0o600,
            ),
            tmpdir.join("home", "bobby", ".ssh", "authorized_keys"): (
                "bobby",
                "bobby",
                0o600,
            ),
        }

        homes = self.create_fake_users(
            [user_bobby],
            mock_permissions,
            m_get_group,
            m_get_owner,
            m_get_permissions,
            m_getpwnam,
            users,
            tmpdir,
        )
        home = homes[0]

        # /tmp/home/bobby/.ssh/authorized_keys = rsa
        authorized_keys = self.create_user_authorized_file(
            home, "authorized_keys", "rsa", keys
        )

        # /tmp/home/bobby/.ssh/user_keys = ed25519
        user_keys = self.create_user_authorized_file(
            home, "user_keys", "ed25519", keys
        )

        authorized_keys_global = self.create_global_authorized_file(
            "etc/ssh/authorized_keys", "ecdsa", keys, tmpdir
        )

        if not inverted:
            options = f"{authorized_keys_global} {user_keys} {authorized_keys}"
        else:
            options = f"{authorized_keys_global} {authorized_keys} {user_keys}"
        sshd_config = self.create_sshd_config(options, tmpdir)

        if not inverted:
            exec_args = (user_bobby, sshd_config, user_keys, keys)
        else:
            exec_args = (user_bobby, sshd_config, authorized_keys, keys)
        self.execute_and_check(*exec_args)

    @patch("cloudinit.ssh_util.pwd.getpwnam")
    @patch("cloudinit.util.get_permissions")
    @patch("cloudinit.util.get_owner")
    @patch("cloudinit.util.get_group")
    def test_single_user_global_file(
        self, m_get_group, m_get_owner, m_get_permissions, m_getpwnam, tmpdir
    ):
        user_bobby = "bobby"
        keys = {}
        users = {}
        mock_permissions = {
            tmpdir.join("home", "bobby"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh", "authorized_keys"): (
                "bobby",
                "bobby",
                0o600,
            ),
        }

        homes = self.create_fake_users(
            [user_bobby],
            mock_permissions,
            m_get_group,
            m_get_owner,
            m_get_permissions,
            m_getpwnam,
            users,
            tmpdir,
        )
        home = homes[0]

        # /tmp/etc/ssh/authorized_keys = rsa
        authorized_keys_global = self.create_global_authorized_file(
            "etc/ssh/authorized_keys", "rsa", keys, tmpdir
        )

        options = "%s" % authorized_keys_global
        sshd_config = self.create_sshd_config(options, tmpdir)

        default = "%s/.ssh/authorized_keys" % home
        self.execute_and_check(user_bobby, sshd_config, default, keys)

    @patch("cloudinit.ssh_util.pwd.getpwnam")
    @patch("cloudinit.util.get_permissions")
    @patch("cloudinit.util.get_owner")
    @patch("cloudinit.util.get_group")
    def test_two_users_local_file_standard(
        self, m_get_group, m_get_owner, m_get_permissions, m_getpwnam, tmpdir
    ):
        keys = {}
        users = {}
        mock_permissions = {
            tmpdir.join("home", "bobby"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh", "authorized_keys"): (
                "bobby",
                "bobby",
                0o600,
            ),
            tmpdir.join("home", "suzie"): ("suzie", "suzie", 0o700),
            tmpdir.join("home", "suzie", ".ssh"): ("suzie", "suzie", 0o700),
            tmpdir.join("home", "suzie", ".ssh", "authorized_keys"): (
                "suzie",
                "suzie",
                0o600,
            ),
        }

        user_bobby = "bobby"
        user_suzie = "suzie"
        homes = self.create_fake_users(
            [user_bobby, user_suzie],
            mock_permissions,
            m_get_group,
            m_get_owner,
            m_get_permissions,
            m_getpwnam,
            users,
            tmpdir,
        )
        home_bobby = homes[0]
        home_suzie = homes[1]

        # /tmp/home/bobby/.ssh/authorized_keys = rsa
        authorized_keys = self.create_user_authorized_file(
            home_bobby, "authorized_keys", "rsa", keys
        )

        # /tmp/home/suzie/.ssh/authorized_keys = rsa
        authorized_keys2 = self.create_user_authorized_file(
            home_suzie, "authorized_keys", "ssh-xmss@openssh.com", keys
        )

        options = ".ssh/authorized_keys"
        sshd_config = self.create_sshd_config(options, tmpdir)

        self.execute_and_check(user_bobby, sshd_config, authorized_keys, keys)
        self.execute_and_check(user_suzie, sshd_config, authorized_keys2, keys)

    @patch("cloudinit.ssh_util.pwd.getpwnam")
    @patch("cloudinit.util.get_permissions")
    @patch("cloudinit.util.get_owner")
    @patch("cloudinit.util.get_group")
    def test_two_users_local_file_custom(
        self, m_get_group, m_get_owner, m_get_permissions, m_getpwnam, tmpdir
    ):
        keys = {}
        users = {}
        mock_permissions = {
            tmpdir.join("home", "bobby"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh", "authorized_keys2"): (
                "bobby",
                "bobby",
                0o600,
            ),
            tmpdir.join("home", "suzie"): ("suzie", "suzie", 0o700),
            tmpdir.join("home", "suzie", ".ssh"): ("suzie", "suzie", 0o700),
            tmpdir.join("home", "suzie", ".ssh", "authorized_keys2"): (
                "suzie",
                "suzie",
                0o600,
            ),
        }

        user_bobby = "bobby"
        user_suzie = "suzie"
        homes = self.create_fake_users(
            [user_bobby, user_suzie],
            mock_permissions,
            m_get_group,
            m_get_owner,
            m_get_permissions,
            m_getpwnam,
            users,
            tmpdir,
        )
        home_bobby = homes[0]
        home_suzie = homes[1]

        # /tmp/home/bobby/.ssh/authorized_keys2 = rsa
        authorized_keys = self.create_user_authorized_file(
            home_bobby, "authorized_keys2", "rsa", keys
        )

        # /tmp/home/suzie/.ssh/authorized_keys2 = rsa
        authorized_keys2 = self.create_user_authorized_file(
            home_suzie, "authorized_keys2", "ssh-xmss@openssh.com", keys
        )

        options = ".ssh/authorized_keys2"
        sshd_config = self.create_sshd_config(options, tmpdir)

        self.execute_and_check(user_bobby, sshd_config, authorized_keys, keys)
        self.execute_and_check(user_suzie, sshd_config, authorized_keys2, keys)

    @patch("cloudinit.ssh_util.pwd.getpwnam")
    @patch("cloudinit.util.get_permissions")
    @patch("cloudinit.util.get_owner")
    @patch("cloudinit.util.get_group")
    def test_two_users_local_global_files(
        self, m_get_group, m_get_owner, m_get_permissions, m_getpwnam, tmpdir
    ):
        keys = {}
        users = {}
        mock_permissions = {
            tmpdir.join("home", "bobby"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh", "authorized_keys2"): (
                "bobby",
                "bobby",
                0o600,
            ),
            tmpdir.join("home", "bobby", ".ssh", "user_keys3"): (
                "bobby",
                "bobby",
                0o600,
            ),
            tmpdir.join("home", "suzie"): ("suzie", "suzie", 0o700),
            tmpdir.join("home", "suzie", ".ssh"): ("suzie", "suzie", 0o700),
            tmpdir.join("home", "suzie", ".ssh", "authorized_keys2"): (
                "suzie",
                "suzie",
                0o600,
            ),
            tmpdir.join("home", "suzie", ".ssh", "user_keys3"): (
                "suzie",
                "suzie",
                0o600,
            ),
        }

        user_bobby = "bobby"
        user_suzie = "suzie"
        homes = self.create_fake_users(
            [user_bobby, user_suzie],
            mock_permissions,
            m_get_group,
            m_get_owner,
            m_get_permissions,
            m_getpwnam,
            users,
            tmpdir,
        )
        home_bobby = homes[0]
        home_suzie = homes[1]

        # /tmp/home/bobby/.ssh/authorized_keys2 = rsa
        self.create_user_authorized_file(
            home_bobby, "authorized_keys2", "rsa", keys
        )
        # /tmp/home/bobby/.ssh/user_keys3 = ed25519
        user_keys = self.create_user_authorized_file(
            home_bobby, "user_keys3", "ed25519", keys
        )

        # /tmp/home/suzie/.ssh/authorized_keys2 = rsa
        authorized_keys2 = self.create_user_authorized_file(
            home_suzie, "authorized_keys2", "ssh-xmss@openssh.com", keys
        )

        # /tmp/etc/ssh/authorized_keys = ecdsa
        authorized_keys_global = self.create_global_authorized_file(
            "etc/ssh/authorized_keys2", "ecdsa", keys, tmpdir
        )

        options = "%s %s %%h/.ssh/authorized_keys2" % (
            authorized_keys_global,
            user_keys,
        )
        sshd_config = self.create_sshd_config(options, tmpdir)

        self.execute_and_check(user_bobby, sshd_config, user_keys, keys)
        self.execute_and_check(user_suzie, sshd_config, authorized_keys2, keys)

    @patch("cloudinit.util.get_user_groups")
    @patch("cloudinit.ssh_util.pwd.getpwnam")
    @patch("cloudinit.util.get_permissions")
    @patch("cloudinit.util.get_owner")
    @patch("cloudinit.util.get_group")
    def test_two_users_local_global_files_badguy(
        self,
        m_get_group,
        m_get_owner,
        m_get_permissions,
        m_getpwnam,
        m_get_user_groups,
        tmpdir,
    ):
        keys = {}
        users = {}
        mock_permissions = {
            tmpdir.join("home", "bobby"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh", "authorized_keys2"): (
                "bobby",
                "bobby",
                0o600,
            ),
            tmpdir.join("home", "bobby", ".ssh", "user_keys3"): (
                "bobby",
                "bobby",
                0o600,
            ),
            tmpdir.join("home", "badguy"): ("root", "root", 0o755),
            tmpdir.join("home", "badguy", "home"): ("root", "root", 0o755),
            tmpdir.join("home", "badguy", "home", "bobby"): (
                "root",
                "root",
                0o655,
            ),
        }

        user_bobby = "bobby"
        user_badguy = "badguy"
        home_bobby, *_ = self.create_fake_users(
            [user_bobby, user_badguy],
            mock_permissions,
            m_get_group,
            m_get_owner,
            m_get_permissions,
            m_getpwnam,
            users,
            tmpdir,
        )
        m_get_user_groups.side_effect = mock_get_user_groups

        # /tmp/home/bobby/.ssh/authorized_keys2 = rsa
        authorized_keys = self.create_user_authorized_file(
            home_bobby, "authorized_keys2", "rsa", keys
        )
        # /tmp/home/bobby/.ssh/user_keys3 = ecdsa
        user_keys = self.create_user_authorized_file(
            home_bobby, "user_keys3", "ecdsa", keys
        )

        # /tmp/home/badguy/home/bobby = ""
        authorized_keys2 = str(tmpdir.join("home", "badguy", "home", "bobby"))
        util.write_file(authorized_keys2, "")

        # /tmp/etc/ssh/authorized_keys = ecdsa
        authorized_keys_global = self.create_global_authorized_file(
            "etc/ssh/authorized_keys2", "ecdsa", keys, tmpdir
        )

        # /tmp/sshd_config
        options = "%s %%h/.ssh/authorized_keys2 %s %s" % (
            authorized_keys2,
            authorized_keys_global,
            user_keys,
        )
        sshd_config = self.create_sshd_config(options, tmpdir)

        self.execute_and_check(user_bobby, sshd_config, authorized_keys, keys)
        self.execute_and_check(
            user_badguy, sshd_config, authorized_keys2, keys
        )

    @patch("cloudinit.util.get_user_groups")
    @patch("cloudinit.ssh_util.pwd.getpwnam")
    @patch("cloudinit.util.get_permissions")
    @patch("cloudinit.util.get_owner")
    @patch("cloudinit.util.get_group")
    def test_two_users_unaccessible_file(
        self,
        m_get_group,
        m_get_owner,
        m_get_permissions,
        m_getpwnam,
        m_get_user_groups,
        tmpdir,
    ):
        keys = {}
        users = {}
        mock_permissions = {
            tmpdir.join("home", "bobby"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh", "authorized_keys"): (
                "bobby",
                "bobby",
                0o600,
            ),
            tmpdir.join("etc"): ("root", "root", 0o755),
            tmpdir.join("etc", "ssh"): ("root", "root", 0o755),
            tmpdir.join("etc", "ssh", "userkeys"): ("root", "root", 0o700),
            tmpdir.join("etc", "ssh", "userkeys", "bobby"): (
                "bobby",
                "bobby",
                0o600,
            ),
            tmpdir.join("etc", "ssh", "userkeys", "badguy"): (
                "badguy",
                "badguy",
                0o600,
            ),
            tmpdir.join("home", "badguy"): ("badguy", "badguy", 0o700),
            tmpdir.join("home", "badguy", ".ssh"): ("badguy", "badguy", 0o700),
            tmpdir.join("home", "badguy", ".ssh", "authorized_keys"): (
                "badguy",
                "badguy",
                0o600,
            ),
        }

        user_bobby = "bobby"
        user_badguy = "badguy"
        homes = self.create_fake_users(
            [user_bobby, user_badguy],
            mock_permissions,
            m_get_group,
            m_get_owner,
            m_get_permissions,
            m_getpwnam,
            users,
            tmpdir,
        )
        m_get_user_groups.side_effect = mock_get_user_groups
        home_bobby = homes[0]
        home_badguy = homes[1]

        # /tmp/home/bobby/.ssh/authorized_keys = rsa
        authorized_keys = self.create_user_authorized_file(
            home_bobby, "authorized_keys", "rsa", keys
        )
        # /tmp/etc/ssh/userkeys/bobby = ecdsa
        # assume here that we can bypass userkeys, despite permissions
        self.create_global_authorized_file(
            "etc/ssh/userkeys/bobby", "ecdsa", keys, tmpdir
        )

        # /tmp/home/badguy/.ssh/authorized_keys = ssh-xmss@openssh.com
        authorized_keys2 = self.create_user_authorized_file(
            home_badguy, "authorized_keys", "ssh-xmss@openssh.com", keys
        )

        # /tmp/etc/ssh/userkeys/badguy = ecdsa
        self.create_global_authorized_file(
            "etc/ssh/userkeys/badguy", "ecdsa", keys, tmpdir
        )

        # /tmp/sshd_config
        options = str(
            tmpdir.join("etc", "ssh", "userkeys", "%u .ssh", "authorized_keys")
        )
        sshd_config = self.create_sshd_config(options, tmpdir)

        self.execute_and_check(user_bobby, sshd_config, authorized_keys, keys)
        self.execute_and_check(
            user_badguy, sshd_config, authorized_keys2, keys
        )

    @patch("cloudinit.util.get_user_groups")
    @patch("cloudinit.ssh_util.pwd.getpwnam")
    @patch("cloudinit.util.get_permissions")
    @patch("cloudinit.util.get_owner")
    @patch("cloudinit.util.get_group")
    def test_two_users_accessible_file(
        self,
        m_get_group,
        m_get_owner,
        m_get_permissions,
        m_getpwnam,
        m_get_user_groups,
        tmpdir,
    ):
        keys = {}
        users = {}
        mock_permissions = {
            tmpdir.join("home", "bobby"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh", "authorized_keys"): (
                "bobby",
                "bobby",
                0o600,
            ),
            tmpdir.join("etc"): ("root", "root", 0o755),
            tmpdir.join("etc", "ssh"): ("root", "root", 0o755),
            tmpdir.join("etc", "ssh", "userkeys"): ("root", "root", 0o755),
            tmpdir.join("etc", "ssh", "userkeys", "bobby"): (
                "bobby",
                "bobby",
                0o600,
            ),
            tmpdir.join("etc", "ssh", "userkeys", "badguy"): (
                "badguy",
                "badguy",
                0o600,
            ),
            tmpdir.join("home", "badguy"): ("badguy", "badguy", 0o700),
            tmpdir.join("home", "badguy", ".ssh"): ("badguy", "badguy", 0o700),
            tmpdir.join("home", "badguy", ".ssh", "authorized_keys"): (
                "badguy",
                "badguy",
                0o600,
            ),
        }

        user_bobby = "bobby"
        user_badguy = "badguy"
        homes = self.create_fake_users(
            [user_bobby, user_badguy],
            mock_permissions,
            m_get_group,
            m_get_owner,
            m_get_permissions,
            m_getpwnam,
            users,
            tmpdir,
        )
        m_get_user_groups.side_effect = mock_get_user_groups
        home_bobby = homes[0]
        home_badguy = homes[1]

        # /tmp/home/bobby/.ssh/authorized_keys = rsa
        self.create_user_authorized_file(
            home_bobby, "authorized_keys", "rsa", keys
        )
        # /tmp/etc/ssh/userkeys/bobby = ed25519
        # assume here that we can bypass userkeys, despite permissions
        authorized_keys = self.create_global_authorized_file(
            "etc/ssh/userkeys/bobby", "ed25519", keys, tmpdir
        )

        # /tmp/home/badguy/.ssh/authorized_keys = ssh-xmss@openssh.com
        self.create_user_authorized_file(
            home_badguy, "authorized_keys", "ssh-xmss@openssh.com", keys
        )

        # /tmp/etc/ssh/userkeys/badguy = ecdsa
        authorized_keys2 = self.create_global_authorized_file(
            "etc/ssh/userkeys/badguy", "ecdsa", keys, tmpdir
        )

        # /tmp/sshd_config
        options = str(
            tmpdir.join("etc", "ssh", "userkeys", "%u .ssh", "authorized_keys")
        )
        sshd_config = self.create_sshd_config(options, tmpdir)

        self.execute_and_check(user_bobby, sshd_config, authorized_keys, keys)
        self.execute_and_check(
            user_badguy, sshd_config, authorized_keys2, keys
        )

    @pytest.mark.parametrize("inverted", [False, True])
    @patch("cloudinit.util.get_user_groups")
    @patch("cloudinit.ssh_util.pwd.getpwnam")
    @patch("cloudinit.util.get_permissions")
    @patch("cloudinit.util.get_owner")
    @patch("cloudinit.util.get_group")
    def test_two_users_hardcoded_single_user_file(
        self,
        m_get_group,
        m_get_owner,
        m_get_permissions,
        m_getpwnam,
        m_get_user_groups,
        inverted,
        tmpdir,
    ):
        keys = {}
        users = {}
        mock_permissions = {
            tmpdir.join("home", "bobby"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh", "authorized_keys"): (
                "bobby",
                "bobby",
                0o600,
            ),
            tmpdir.join("home", "suzie"): ("suzie", "suzie", 0o700),
            tmpdir.join("home", "suzie", ".ssh"): ("suzie", "suzie", 0o700),
            tmpdir.join("home", "suzie", ".ssh", "authorized_keys"): (
                "suzie",
                "suzie",
                0o600,
            ),
        }

        user_bobby = "bobby"
        user_suzie = "suzie"
        homes = self.create_fake_users(
            [user_bobby, user_suzie],
            mock_permissions,
            m_get_group,
            m_get_owner,
            m_get_permissions,
            m_getpwnam,
            users,
            tmpdir,
        )
        home_bobby = homes[0]
        home_suzie = homes[1]
        m_get_user_groups.side_effect = mock_get_user_groups

        # /tmp/home/bobby/.ssh/authorized_keys = rsa
        authorized_keys = self.create_user_authorized_file(
            home_bobby, "authorized_keys", "rsa", keys
        )

        # /tmp/home/suzie/.ssh/authorized_keys = ssh-xmss@openssh.com
        authorized_keys2 = self.create_user_authorized_file(
            home_suzie, "authorized_keys", "ssh-xmss@openssh.com", keys
        )

        # /tmp/sshd_config
        if not inverted:
            expected_keys = authorized_keys
        else:
            expected_keys = authorized_keys2
        options = "%s" % (expected_keys)
        sshd_config = self.create_sshd_config(options, tmpdir)

        if not inverted:
            expected_bobby = expected_keys
            expected_suzie = "%s/.ssh/authorized_keys" % home_suzie
        else:
            expected_bobby = "%s/.ssh/authorized_keys" % home_bobby
            expected_suzie = expected_keys
        self.execute_and_check(user_bobby, sshd_config, expected_bobby, keys)
        self.execute_and_check(user_suzie, sshd_config, expected_suzie, keys)

    @patch("cloudinit.util.get_user_groups")
    @patch("cloudinit.ssh_util.pwd.getpwnam")
    @patch("cloudinit.util.get_permissions")
    @patch("cloudinit.util.get_owner")
    @patch("cloudinit.util.get_group")
    def test_two_users_hardcoded_user_files(
        self,
        m_get_group,
        m_get_owner,
        m_get_permissions,
        m_getpwnam,
        m_get_user_groups,
        tmpdir,
    ):
        keys = {}
        users = {}
        mock_permissions = {
            tmpdir.join("home", "bobby"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh"): ("bobby", "bobby", 0o700),
            tmpdir.join("home", "bobby", ".ssh", "authorized_keys"): (
                "bobby",
                "bobby",
                0o600,
            ),
            tmpdir.join("home", "suzie"): ("suzie", "suzie", 0o700),
            tmpdir.join("home", "suzie", ".ssh"): ("suzie", "suzie", 0o700),
            tmpdir.join("home", "suzie", ".ssh", "authorized_keys"): (
                "suzie",
                "suzie",
                0o600,
            ),
        }

        user_bobby = "bobby"
        user_suzie = "suzie"
        homes = self.create_fake_users(
            [user_bobby, user_suzie],
            mock_permissions,
            m_get_group,
            m_get_owner,
            m_get_permissions,
            m_getpwnam,
            users,
            tmpdir,
        )
        home_bobby = homes[0]
        home_suzie = homes[1]
        m_get_user_groups.side_effect = mock_get_user_groups

        # /tmp/home/bobby/.ssh/authorized_keys = rsa
        authorized_keys = self.create_user_authorized_file(
            home_bobby, "authorized_keys", "rsa", keys
        )

        # /tmp/home/suzie/.ssh/authorized_keys = ssh-xmss@openssh.com
        authorized_keys2 = self.create_user_authorized_file(
            home_suzie, "authorized_keys", "ssh-xmss@openssh.com", keys
        )

        # /tmp/etc/ssh/authorized_keys = ecdsa
        authorized_keys_global = self.create_global_authorized_file(
            "etc/ssh/authorized_keys", "ecdsa", keys, tmpdir
        )

        # /tmp/sshd_config
        options = "%s %s %s" % (
            authorized_keys_global,
            authorized_keys,
            authorized_keys2,
        )
        sshd_config = self.create_sshd_config(options, tmpdir)

        self.execute_and_check(user_bobby, sshd_config, authorized_keys, keys)
        self.execute_and_check(user_suzie, sshd_config, authorized_keys2, keys)
