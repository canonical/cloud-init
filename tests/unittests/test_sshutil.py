# This file is part of cloud-init. See LICENSE file for license information.

from collections import namedtuple
from unittest.mock import patch

from cloudinit import ssh_util
from cloudinit.tests import helpers as test_helpers
from cloudinit import util

# https://stackoverflow.com/questions/11351032/
FakePwEnt = namedtuple(
    'FakePwEnt',
    ['pw_dir', 'pw_gecos', 'pw_name', 'pw_passwd', 'pw_shell', 'pwd_uid'])
FakePwEnt.__new__.__defaults__ = tuple(
    "UNSET_%s" % n for n in FakePwEnt._fields)


# Do not use these public keys, most of them are fetched from
# the testdata for OpenSSH, and their private keys are available
# https://github.com/openssh/openssh-portable/tree/master/regress/unittests/sshkey/testdata
VALID_CONTENT = {
    'dsa': (
        "AAAAB3NzaC1kc3MAAACBAIrjOQSlSea19bExXBMBKBvcLhBoVvNBjCppNzllipF"
        "W4jgIOMcNanULRrZGjkOKat6MWJNetSbV1E6IOFDQ16rQgsh/OvYU9XhzM8seLa"
        "A21VszZuhIV7/2DE3vxu7B54zVzueG1O1Deq6goQCRGWBUnqO2yluJiG4HzrnDa"
        "jzRAAAAFQDMPO96qXd4F5A+5b2f2MO7SpVomQAAAIBpC3K2zIbDLqBBs1fn7rsv"
        "KcJvwihdlVjG7UXsDB76P2GNqVG+IlYPpJZ8TO/B/fzTMtrdXp9pSm9OY1+BgN4"
        "REsZ2WNcvfgY33aWaEM+ieCcQigvxrNAF2FTVcbUIIxAn6SmHuQSWrLSfdHc8H7"
        "hsrgeUPPdzjBD/cv2ZmqwZ1AAAAIAplIsScrJut5wJMgyK1JG0Kbw9JYQpLe95P"
        "obB069g8+mYR8U0fysmTEdR44mMu0VNU5E5OhTYoTGfXrVrkR134LqFM2zpVVbE"
        "JNDnIqDHxTkc6LY2vu8Y2pQ3/bVnllZZOda2oD5HQ7ovygQa6CH+fbaZHbdDUX/"
        "5z7u2rVAlDw=="
    ),
    'ecdsa': (
        "AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBITrGBB3cgJ"
        "J7fPxvtMW9H3oRisNpJ3OAslxZeyP7I0A9BPAW0RQIwHVtVnM7zrp4nI+JLZov/"
        "Ql7lc2leWL7CY="
    ),
    'rsa': (
        "AAAAB3NzaC1yc2EAAAABIwAAAQEA3I7VUf2l5gSn5uavROsc5HRDpZdQueUq5oz"
        "emNSj8T7enqKHOEaFoU2VoPgGEWC9RyzSQVeyD6s7APMcE82EtmW4skVEgEGSbD"
        "c1pvxzxtchBj78hJP6Cf5TCMFSXw+Fz5rF1dR23QDbN1mkHs7adr8GW4kSWqU7Q"
        "7NDwfIrJJtO7Hi42GyXtvEONHbiRPOe8stqUly7MvUoN+5kfjBM8Qqpfl2+FNhT"
        "YWpMfYdPUnE7u536WqzFmsaqJctz3gBxH9Ex7dFtrxR4qiqEr9Qtlu3xGn7Bw07"
        "/+i1D+ey3ONkZLN+LQ714cgj8fRS4Hj29SCmXp5Kt5/82cD/VN3NtHw=="
    ),
    'ed25519': (
        "AAAAC3NzaC1lZDI1NTE5AAAAIA1J77+CrJ8p6/vWCEzuylqJNMHUP/XmeYyGVWb"
        "8lnDd"
    ),
    'ecdsa-sha2-nistp256-cert-v01@openssh.com': (
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
    'ecdsa-sha2-nistp256': (
        "AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEjA0gjJmPM"
        "6La3sXyfNlnjilvvGY6I2M8SvJj4o3X/46wcUbPWTaj4RF3EXwHvNxplYBwdPlk"
        "2zEecvf9Cs2BM="
    ),
    'ecdsa-sha2-nistp384-cert-v01@openssh.com': (
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
    'ecdsa-sha2-nistp384': (
        "AAAAE2VjZHNhLXNoYTItbmlzdHAzODQAAAAIbmlzdHAzODQAAABhBAaYSQs+8TT"
        "0Tzciy0dorwhur6yzOGUrYQ6ueUQYWbE7eNdHmhsVrlpGPgSaYByhXtAJiPOMqL"
        "U5h0eb3sCtM3ek4NvjXFTGTqPrrxJI6q0OsgrtkGE7UM9ZsfMm7q6BOA=="
    ),
    'ecdsa-sha2-nistp521-cert-v01@openssh.com': (
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
    'ecdsa-sha2-nistp521': (
        "AAAAE2VjZHNhLXNoYTItbmlzdHA1MjEAAAAIbmlzdHA1MjEAAACFBAHosAOHAI1"
        "ZkerbKYQ72S6uit1u77PCj/OalZtXgsxv0TTAZB273puG2X94CQ8yyNHcby87zF"
        "ZHdv5BSKyZ/cyREAAeiAcSakop9VS3+bUfZpEIqwBZXarwUjnRnxprkcQ0rfCCd"
        "agkGZr/OA7DemK2D8tKLTHsKoEEWNImo6/pXDkFxA=="
    ),
    'sk-ecdsa-sha2-nistp256-cert-v01@openssh.com': (
        "AAAAIHNzaC1lZDI1NTE5LWNlcnQtdjAxQG9wZW5zc2guY29tAAAAIIxzuxl4z3u"
        "wAIslne8Huft+1n1IhHAlNbWZkQyyECCGAAAAIFOG6kY7Rf4UtCFvPwKgo/BztX"
        "ck2xC4a2WyA34XtIwZAAAAAAAAAAgAAAACAAAABmp1bGl1cwAAABIAAAAFaG9zd"
        "DEAAAAFaG9zdDIAAAAANowB8AAAAABNHmBwAAAAAAAAAAAAAAAAAAAAMwAAAAtz"
        "c2gtZWQyNTUxOQAAACBThupGO0X+FLQhbz8CoKPwc7V3JNsQuGtlsgN+F7SMGQA"
        "AAFMAAAALc3NoLWVkMjU1MTkAAABABGTn+Bmz86Ajk+iqKCSdP5NClsYzn4alJd"
        "0V5bizhP0Kumc/HbqQfSt684J1WdSzih+EjvnTgBhK9jTBKb90AQ=="
    ),
    'sk-ecdsa-sha2-nistp256@openssh.com': (
        "AAAAInNrLWVjZHNhLXNoYTItbmlzdHAyNTZAb3BlbnNzaC5jb20AAAAIbmlzdHA"
        "yNTYAAABBBIELQJ2DgvaX1yQlKFokfWM2suuaCFI2qp0eJodHyg6O4ifxc3XpRK"
        "d1OS8dNYQtE/YjdXSrA+AOnMF5ns2Nkx4AAAAEc3NoOg=="
    ),
    'sk-ssh-ed25519-cert-v01@openssh.com': (
        "AAAAIHNzaC1lZDI1NTE5LWNlcnQtdjAxQG9wZW5zc2guY29tAAAAIIxzuxl4z3u"
        "wAIslne8Huft+1n1IhHAlNbWZkQyyECCGAAAAIFOG6kY7Rf4UtCFvPwKgo/BztX"
        "ck2xC4a2WyA34XtIwZAAAAAAAAAAgAAAACAAAABmp1bGl1cwAAABIAAAAFaG9zd"
        "DEAAAAFaG9zdDIAAAAANowB8AAAAABNHmBwAAAAAAAAAAAAAAAAAAAAMwAAAAtz"
        "c2gtZWQyNTUxOQAAACBThupGO0X+FLQhbz8CoKPwc7V3JNsQuGtlsgN+F7SMGQA"
        "AAFMAAAALc3NoLWVkMjU1MTkAAABABGTn+Bmz86Ajk+iqKCSdP5NClsYzn4alJd"
        "0V5bizhP0Kumc/HbqQfSt684J1WdSzih+EjvnTgBhK9jTBKb90AQ=="
    ),
    'sk-ssh-ed25519@openssh.com': (
        "AAAAGnNrLXNzaC1lZDI1NTE5QG9wZW5zc2guY29tAAAAICFo/k5LU8863u66YC9"
        "eUO2170QduohPURkQnbLa/dczAAAABHNzaDo="
    ),
    'ssh-dss-cert-v01@openssh.com': (
        "AAAAHHNzaC1kc3MtY2VydC12MDFAb3BlbnNzaC5jb20AAAAgdTlbNU9Hn9Qng3F"
        "HxwH971bxCIoq1ern/QWFFDWXgmYAAACBAPqS600VGwdPAQC/p3f0uGyrLVql0c"
        "Fn1zYd/JGvtabKnIYjLaYprje/NcjwI3CZFJiz4Dp3S8kLs+X5/1DMn/Tg1Y4D4"
        "yLB+6vCtHcJF7rVBFhvw/KZwc7G54ez3khyOtsg82fzpyOc8/mq+/+C5TMKO7DD"
        "jMF0k5emWKCsa3ZfAAAAFQCjA/+dKkMu4/CWjJPtfl7YNaStNQAAAIEA7uX1BVV"
        "tJKjLmWrpw62+l/xSXA5rr7MHBuWjiCYV3VHBfXJaQDyRDtGuEJKDwdzqYgacpG"
        "ApGWL/cuBtJ9nShsUl6GRG0Ra03g+Hx9VR5LviJBsjAVB4qVgciU1NGga0Bt2Le"
        "cd1X4EGQRBzVXeuOpiqGM6jP/I2yDMs0Pboet0AAACBAOdXpyfmobEBaOqZAuvg"
        "j1P0uhjG2P31Ufurv22FWPBU3A9qrkxbOXwE0LwvjCvrsQV/lrYhJz/tiys40Ve"
        "ahulWZE5SAHMXGIf95LiLSgaXMjko7joot+LK84ltLymwZ4QMnYjnZSSclf1Uuy"
        "QMcUtb34+I0u9Ycnyhp2mSFsQtAAAAAAAAAAYAAAACAAAABmp1bGl1cwAAABIAA"
        "AAFaG9zdDEAAAAFaG9zdDIAAAAANowB8AAAAABNHmBwAAAAAAAAAAAAAAAAAAAA"
        "MwAAAAtzc2gtZWQyNTUxOQAAACBThupGO0X+FLQhbz8CoKPwc7V3JNsQuGtlsgN"
        "+F7SMGQAAAFMAAAALc3NoLWVkMjU1MTkAAABAh/z1LIdNL1b66tQ8t9DY9BTB3B"
        "QKpTKmc7ezyFKLwl96yaIniZwD9Ticdbe/8i/Li3uCFE3EAt8NAIv9zff8Bg=="
    ),
    'ssh-dss': (
        "AAAAB3NzaC1kc3MAAACBAPqS600VGwdPAQC/p3f0uGyrLVql0cFn1zYd/JGvtab"
        "KnIYjLaYprje/NcjwI3CZFJiz4Dp3S8kLs+X5/1DMn/Tg1Y4D4yLB+6vCtHcJF7"
        "rVBFhvw/KZwc7G54ez3khyOtsg82fzpyOc8/mq+/+C5TMKO7DDjMF0k5emWKCsa"
        "3ZfAAAAFQCjA/+dKkMu4/CWjJPtfl7YNaStNQAAAIEA7uX1BVVtJKjLmWrpw62+"
        "l/xSXA5rr7MHBuWjiCYV3VHBfXJaQDyRDtGuEJKDwdzqYgacpGApGWL/cuBtJ9n"
        "ShsUl6GRG0Ra03g+Hx9VR5LviJBsjAVB4qVgciU1NGga0Bt2Lecd1X4EGQRBzVX"
        "euOpiqGM6jP/I2yDMs0Pboet0AAACBAOdXpyfmobEBaOqZAuvgj1P0uhjG2P31U"
        "furv22FWPBU3A9qrkxbOXwE0LwvjCvrsQV/lrYhJz/tiys40VeahulWZE5SAHMX"
        "GIf95LiLSgaXMjko7joot+LK84ltLymwZ4QMnYjnZSSclf1UuyQMcUtb34+I0u9"
        "Ycnyhp2mSFsQt"
    ),
    'ssh-ed25519-cert-v01@openssh.com': (
        "AAAAIHNzaC1lZDI1NTE5LWNlcnQtdjAxQG9wZW5zc2guY29tAAAAIIxzuxl4z3u"
        "wAIslne8Huft+1n1IhHAlNbWZkQyyECCGAAAAIFOG6kY7Rf4UtCFvPwKgo/BztX"
        "ck2xC4a2WyA34XtIwZAAAAAAAAAAgAAAACAAAABmp1bGl1cwAAABIAAAAFaG9zd"
        "DEAAAAFaG9zdDIAAAAANowB8AAAAABNHmBwAAAAAAAAAAAAAAAAAAAAMwAAAAtz"
        "c2gtZWQyNTUxOQAAACBThupGO0X+FLQhbz8CoKPwc7V3JNsQuGtlsgN+F7SMGQA"
        "AAFMAAAALc3NoLWVkMjU1MTkAAABABGTn+Bmz86Ajk+iqKCSdP5NClsYzn4alJd"
        "0V5bizhP0Kumc/HbqQfSt684J1WdSzih+EjvnTgBhK9jTBKb90AQ=="
    ),
    'ssh-ed25519': (
        "AAAAC3NzaC1lZDI1NTE5AAAAIFOG6kY7Rf4UtCFvPwKgo/BztXck2xC4a2WyA34"
        "XtIwZ"
    ),
    'ssh-rsa-cert-v01@openssh.com': (
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
    'ssh-rsa': (
        "AAAAB3NzaC1yc2EAAAADAQABAAAAgQDLV5lUTt7FrADseB/CGhEZzpoojjEW5y8"
        "+ePvLppmK3MmMI18ud6vxzpK3bwZLYkVSyfJYI0HmIuGhdu7yMrW6wb84gbq8C3"
        "1Xoe9EORcIUuGSvDKdNSM1SjlhDquRblDFB8kToqXyx1lqrXecXylxIUOL0jE+u"
        "0rU1967pDJx+w=="
    ),
    'ssh-xmss-cert-v01@openssh.com': (
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
    'ssh-xmss@openssh.com': (
        "AAAAFHNzaC14bXNzQG9wZW5zc2guY29tAAAAFVhNU1NfU0hBMi0yNTZfVzE2X0g"
        "xMAAAAECqptWnK94d+Sj2xcdTu8gz+75lawZoLSZFqC5IhbYuT/Z3oBZCim6yt+"
        "HAmk6MKldl3Fg+74v4sR/SII0I0Jv/"
    ),
}

KEY_TYPES = list(VALID_CONTENT.keys())

TEST_OPTIONS = (
    "no-port-forwarding,no-agent-forwarding,no-X11-forwarding,"
    'command="echo \'Please login as the user \"ubuntu\" rather than the'
    'user \"root\".\';echo;sleep 10"')


class TestAuthKeyLineParser(test_helpers.CiTestCase):

    def test_simple_parse(self):
        # test key line with common 3 fields (keytype, base64, comment)
        parser = ssh_util.AuthKeyLineParser()
        for ktype in KEY_TYPES:
            content = VALID_CONTENT[ktype]
            comment = 'user-%s@host' % ktype
            line = ' '.join((ktype, content, comment,))
            key = parser.parse(line)

            self.assertEqual(key.base64, content)
            self.assertFalse(key.options)
            self.assertEqual(key.comment, comment)
            self.assertEqual(key.keytype, ktype)

    def test_parse_no_comment(self):
        # test key line with key type and base64 only
        parser = ssh_util.AuthKeyLineParser()
        for ktype in KEY_TYPES:
            content = VALID_CONTENT[ktype]
            line = ' '.join((ktype, content,))
            key = parser.parse(line)

            self.assertEqual(key.base64, content)
            self.assertFalse(key.options)
            self.assertFalse(key.comment)
            self.assertEqual(key.keytype, ktype)

    def test_parse_with_keyoptions(self):
        # test key line with options in it
        parser = ssh_util.AuthKeyLineParser()
        options = TEST_OPTIONS
        for ktype in KEY_TYPES:
            content = VALID_CONTENT[ktype]
            comment = 'user-%s@host' % ktype
            line = ' '.join((options, ktype, content, comment,))
            key = parser.parse(line)

            self.assertEqual(key.base64, content)
            self.assertEqual(key.options, options)
            self.assertEqual(key.comment, comment)
            self.assertEqual(key.keytype, ktype)

    def test_parse_with_options_passed_in(self):
        # test key line with key type and base64 only
        parser = ssh_util.AuthKeyLineParser()

        baseline = ' '.join(("rsa", VALID_CONTENT['rsa'], "user@host"))
        myopts = "no-port-forwarding,no-agent-forwarding"

        key = parser.parse("allowedopt" + " " + baseline)
        self.assertEqual(key.options, "allowedopt")

        key = parser.parse("overridden_opt " + baseline, options=myopts)
        self.assertEqual(key.options, myopts)

    def test_parse_invalid_keytype(self):
        parser = ssh_util.AuthKeyLineParser()
        key = parser.parse(' '.join(["badkeytype", VALID_CONTENT['rsa']]))

        self.assertFalse(key.valid())


class TestUpdateAuthorizedKeys(test_helpers.CiTestCase):

    def test_new_keys_replace(self):
        """new entries with the same base64 should replace old."""
        orig_entries = [
            ' '.join(('rsa', VALID_CONTENT['rsa'], 'orig_comment1')),
            ' '.join(('dsa', VALID_CONTENT['dsa'], 'orig_comment2'))]

        new_entries = [
            ' '.join(('rsa', VALID_CONTENT['rsa'], 'new_comment1')), ]

        expected = '\n'.join([new_entries[0], orig_entries[1]]) + '\n'

        parser = ssh_util.AuthKeyLineParser()
        found = ssh_util.update_authorized_keys(
            [parser.parse(p) for p in orig_entries],
            [parser.parse(p) for p in new_entries])

        self.assertEqual(expected, found)

    def test_new_invalid_keys_are_ignored(self):
        """new entries that are invalid should be skipped."""
        orig_entries = [
            ' '.join(('rsa', VALID_CONTENT['rsa'], 'orig_comment1')),
            ' '.join(('dsa', VALID_CONTENT['dsa'], 'orig_comment2'))]

        new_entries = [
            ' '.join(('rsa', VALID_CONTENT['rsa'], 'new_comment1')),
            'xxx-invalid-thing1',
            'xxx-invalid-blob2'
        ]

        expected = '\n'.join([new_entries[0], orig_entries[1]]) + '\n'

        parser = ssh_util.AuthKeyLineParser()
        found = ssh_util.update_authorized_keys(
            [parser.parse(p) for p in orig_entries],
            [parser.parse(p) for p in new_entries])

        self.assertEqual(expected, found)


class TestParseSSHConfig(test_helpers.CiTestCase):

    def setUp(self):
        self.load_file_patch = patch('cloudinit.ssh_util.util.load_file')
        self.load_file = self.load_file_patch.start()
        self.isfile_patch = patch('cloudinit.ssh_util.os.path.isfile')
        self.isfile = self.isfile_patch.start()
        self.isfile.return_value = True

    def tearDown(self):
        self.load_file_patch.stop()
        self.isfile_patch.stop()

    def test_not_a_file(self):
        self.isfile.return_value = False
        self.load_file.side_effect = IOError
        ret = ssh_util.parse_ssh_config('not a real file')
        self.assertEqual([], ret)

    def test_empty_file(self):
        self.load_file.return_value = ''
        ret = ssh_util.parse_ssh_config('some real file')
        self.assertEqual([], ret)

    def test_comment_line(self):
        comment_line = '# This is a comment'
        self.load_file.return_value = comment_line
        ret = ssh_util.parse_ssh_config('some real file')
        self.assertEqual(1, len(ret))
        self.assertEqual(comment_line, ret[0].line)

    def test_blank_lines(self):
        lines = ['', '\t', ' ']
        self.load_file.return_value = '\n'.join(lines)
        ret = ssh_util.parse_ssh_config('some real file')
        self.assertEqual(len(lines), len(ret))
        for line in ret:
            self.assertEqual('', line.line)

    def test_lower_case_config(self):
        self.load_file.return_value = 'foo bar'
        ret = ssh_util.parse_ssh_config('some real file')
        self.assertEqual(1, len(ret))
        self.assertEqual('foo', ret[0].key)
        self.assertEqual('bar', ret[0].value)

    def test_upper_case_config(self):
        self.load_file.return_value = 'Foo Bar'
        ret = ssh_util.parse_ssh_config('some real file')
        self.assertEqual(1, len(ret))
        self.assertEqual('foo', ret[0].key)
        self.assertEqual('Bar', ret[0].value)

    def test_lower_case_with_equals(self):
        self.load_file.return_value = 'foo=bar'
        ret = ssh_util.parse_ssh_config('some real file')
        self.assertEqual(1, len(ret))
        self.assertEqual('foo', ret[0].key)
        self.assertEqual('bar', ret[0].value)

    def test_upper_case_with_equals(self):
        self.load_file.return_value = 'Foo=bar'
        ret = ssh_util.parse_ssh_config('some real file')
        self.assertEqual(1, len(ret))
        self.assertEqual('foo', ret[0].key)
        self.assertEqual('bar', ret[0].value)


class TestUpdateSshConfigLines(test_helpers.CiTestCase):
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
        self.assertEqual(line.key, opt.lower())
        self.assertEqual(line.value, val)
        self.assertIn(opt, str(line))
        self.assertIn(val, str(line))

    def test_new_option_added(self):
        """A single update of non-existing option."""
        lines = ssh_util.parse_ssh_config_lines(list(self.exlines))
        result = ssh_util.update_ssh_config_lines(lines, {'MyKey': 'MyVal'})
        self.assertEqual(['MyKey'], result)
        self.check_line(lines[-1], "MyKey", "MyVal")

    def test_commented_out_not_updated_but_appended(self):
        """Implementation does not un-comment and update lines."""
        lines = ssh_util.parse_ssh_config_lines(list(self.exlines))
        result = ssh_util.update_ssh_config_lines(lines, {self.pwauth: "no"})
        self.assertEqual([self.pwauth], result)
        self.check_line(lines[-1], self.pwauth, "no")

    def test_single_option_updated(self):
        """A single update should have change made and line updated."""
        opt, val = ("UsePAM", "no")
        lines = ssh_util.parse_ssh_config_lines(list(self.exlines))
        result = ssh_util.update_ssh_config_lines(lines, {opt: val})
        self.assertEqual([opt], result)
        self.check_line(lines[1], opt, val)

    def test_multiple_updates_with_add(self):
        """Verify multiple updates some added some changed, some not."""
        updates = {"UsePAM": "no", "X11Forwarding": "no", "NewOpt": "newval",
                   "AcceptEnv": "LANG ADD LC_*"}
        lines = ssh_util.parse_ssh_config_lines(list(self.exlines))
        result = ssh_util.update_ssh_config_lines(lines, updates)
        self.assertEqual(set(["UsePAM", "NewOpt", "AcceptEnv"]), set(result))
        self.check_line(lines[3], "AcceptEnv", updates["AcceptEnv"])

    def test_return_empty_if_no_changes(self):
        """If there are no changes, then return should be empty list."""
        updates = {"UsePAM": "yes"}
        lines = ssh_util.parse_ssh_config_lines(list(self.exlines))
        result = ssh_util.update_ssh_config_lines(lines, updates)
        self.assertEqual([], result)
        self.assertEqual(self.exlines, [str(line) for line in lines])

    def test_keycase_not_modified(self):
        """Original case of key should not be changed on update.
        This behavior is to keep original config as much intact as can be."""
        updates = {"usepam": "no"}
        lines = ssh_util.parse_ssh_config_lines(list(self.exlines))
        result = ssh_util.update_ssh_config_lines(lines, updates)
        self.assertEqual(["usepam"], result)
        self.assertEqual("UsePAM no", str(lines[1]))


class TestUpdateSshConfig(test_helpers.CiTestCase):
    cfgdata = '\n'.join(["#Option val", "MyKey ORIG_VAL", ""])

    def test_modified(self):
        mycfg = self.tmp_path("ssh_config_1")
        util.write_file(mycfg, self.cfgdata)
        ret = ssh_util.update_ssh_config({"MyKey": "NEW_VAL"}, mycfg)
        self.assertTrue(ret)
        found = util.load_file(mycfg)
        self.assertEqual(self.cfgdata.replace("ORIG_VAL", "NEW_VAL"), found)
        # assert there is a newline at end of file (LP: #1677205)
        self.assertEqual('\n', found[-1])

    def test_not_modified(self):
        mycfg = self.tmp_path("ssh_config_2")
        util.write_file(mycfg, self.cfgdata)
        with patch("cloudinit.ssh_util.util.write_file") as m_write_file:
            ret = ssh_util.update_ssh_config({"MyKey": "ORIG_VAL"}, mycfg)
        self.assertFalse(ret)
        self.assertEqual(self.cfgdata, util.load_file(mycfg))
        m_write_file.assert_not_called()


class TestBasicAuthorizedKeyParse(test_helpers.CiTestCase):
    def test_user(self):
        self.assertEqual(
            ["/opt/bobby/keys"],
            ssh_util.render_authorizedkeysfile_paths(
                "/opt/%u/keys", "/home/bobby", "bobby"))

    def test_multiple(self):
        self.assertEqual(
            ["/keys/path1", "/keys/path2"],
            ssh_util.render_authorizedkeysfile_paths(
                "/keys/path1 /keys/path2", "/home/bobby", "bobby"))

    def test_relative(self):
        self.assertEqual(
            ["/home/bobby/.secret/keys"],
            ssh_util.render_authorizedkeysfile_paths(
                ".secret/keys", "/home/bobby", "bobby"))

    def test_home(self):
        self.assertEqual(
            ["/homedirs/bobby/.keys"],
            ssh_util.render_authorizedkeysfile_paths(
                "%h/.keys", "/homedirs/bobby", "bobby"))


class TestMultipleSshAuthorizedKeysFile(test_helpers.CiTestCase):

    @patch("cloudinit.ssh_util.pwd.getpwnam")
    def test_multiple_authorizedkeys_file_order1(self, m_getpwnam):
        fpw = FakePwEnt(pw_name='bobby', pw_dir='/home2/bobby')
        m_getpwnam.return_value = fpw
        authorized_keys = self.tmp_path('authorized_keys')
        util.write_file(authorized_keys, VALID_CONTENT['rsa'])

        user_keys = self.tmp_path('user_keys')
        util.write_file(user_keys, VALID_CONTENT['dsa'])

        sshd_config = self.tmp_path('sshd_config')
        util.write_file(
            sshd_config,
            "AuthorizedKeysFile %s %s" % (authorized_keys, user_keys)
        )

        (auth_key_fn, auth_key_entries) = ssh_util.extract_authorized_keys(
            fpw.pw_name, sshd_config)
        content = ssh_util.update_authorized_keys(auth_key_entries, [])

        self.assertEqual("%s/.ssh/authorized_keys" % fpw.pw_dir, auth_key_fn)
        self.assertTrue(VALID_CONTENT['rsa'] in content)
        self.assertTrue(VALID_CONTENT['dsa'] in content)

    @patch("cloudinit.ssh_util.pwd.getpwnam")
    def test_multiple_authorizedkeys_file_order2(self, m_getpwnam):
        fpw = FakePwEnt(pw_name='suzie', pw_dir='/home/suzie')
        m_getpwnam.return_value = fpw
        authorized_keys = self.tmp_path('authorized_keys')
        util.write_file(authorized_keys, VALID_CONTENT['rsa'])

        user_keys = self.tmp_path('user_keys')
        util.write_file(user_keys, VALID_CONTENT['dsa'])

        sshd_config = self.tmp_path('sshd_config')
        util.write_file(
            sshd_config,
            "AuthorizedKeysFile %s %s" % (authorized_keys, user_keys)
        )

        (auth_key_fn, auth_key_entries) = ssh_util.extract_authorized_keys(
            fpw.pw_name, sshd_config
        )
        content = ssh_util.update_authorized_keys(auth_key_entries, [])

        self.assertEqual("%s/.ssh/authorized_keys" % fpw.pw_dir, auth_key_fn)
        self.assertTrue(VALID_CONTENT['rsa'] in content)
        self.assertTrue(VALID_CONTENT['dsa'] in content)

# vi: ts=4 expandtab
