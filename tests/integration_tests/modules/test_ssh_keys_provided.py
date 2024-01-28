"""Integration test for the ssh module.

This test specifies keys to be provided to the system through the ``ssh``
module and then checks that if those keys were successfully added to the
system.

(This is ported from
``tests/cloud_tests/testcases/modules/ssh_keys_provided.yaml''``.)"""

import pytest

from tests.integration_tests.releases import CURRENT_RELEASE

USER_DATA = """\
#cloud-config
disable_root: false
ssh_authorized_keys:
  - ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDXW9Gg5H7ehjdSc6qDzwNtgCy94XYHhEYlXZMO2+FJrH3wfHGiMfCwOHxcOMt2QiXItULthdeQWS9QjBSSjVRXf6731igFrqPFyS9qBlOQ5D29C4HBXFnQggGVpBNJ82IRJv7szbbe/vpgLBP4kttUza9Dr4e1YM1ln4PRnjfXea6T0m+m1ixNb5432pTXlqYOnNOxSIm1gHgMLxPuDrJvQERDKrSiKSjIdyC9Jd8t2e1tkNLY0stmckVRbhShmcJvlyofHWbc2Ca1mmtP7MlS1VQnfLkvU1IrFwkmaQmaggX6WR6coRJ6XFXdWcq/AI2K6GjSnl1dnnCxE8VCEXBlXgFzad+PMSG4yiL5j8Oo1ZVpkTdgBnw4okGqTYCXyZg6X00As9IBNQfZMFlQXlIo4FiWgj3CO5QHQOyOX6FuEumaU13GnERrSSdp9tCs1Qm3/DG2RSCQBWTfcgMcStIvKqvJ3IjFn0vGLvI3Ampnq9q1SHwmmzAPSdzcMA76HyMUA5VWaBvWHlUxzIM6unxZASnwvuCzpywSEB5J2OF+p6H+cStJwQ32XwmOG8pLp1srlVWpqZI58Du/lzrkPqONphoZx0LDV86w7RUz1ksDzAdcm0tvmNRFMN1a0frDs506oA3aWK0oDk4Nmvk8sXGTYYw3iQSkOvDUUlIsqdaO+w==
ssh_keys:
  rsa_private: |
    -----BEGIN RSA PRIVATE KEY-----
    MIIEowIBAAKCAQEAtPx6PqN3iSEsnTtibyIEy52Tra8T5fn0ryXyg46Di2NBwdnj
    o8trNv9jenfV/UhmePl58lXjT43wV8OCMl6KsYXyBdegM35NNtono4I4mLLKFMR9
    9TOtDn6iYcaNenVhF3ZCj9Z2nNOlTrdc0uchHqKMrxLjCRCUrL91Uf+xioTF901Y
    RM+ZqC5lT92yAL76F4qPF+Lq1QtUfNfUIwwvOp5ccDZLPxij0YvyBzubYye9hJHu
    yjbJv78R4JHV+L2WhzSoX3W/6WrxVzeXqFGqH894ccOaC/7tnqSP6V8lIQ6fE2+c
    DurJcpM3CJRgkndGHjtU55Y71YkcdLksSMvezQIDAQABAoIBAQCrU4IJP8dNeaj5
    IpkY6NQvR/jfZqfogYi+MKb1IHin/4rlDfUvPcY9pt8ttLlObjYK+OcWn3Vx/sRw
    4DOkqNiUGl80Zp1RgZNohHUXlJMtAbrIlAVEk+mTmg7vjfyp2unRQvLZpMRdywBm
    lq95OrCghnG03aUsFJUZPpi5ydnwbA12ma+KHkG0EzaVlhA7X9N6z0K6U+zue2gl
    goMLt/MH0rsYawkHrwiwXaIFQeyV4MJP0vmrZLbFk1bycu9X/xPtTYotWyWo4eKA
    cb05uu04qwexkKHDM0KXtT0JecbTo2rOefFo8Uuab6uJY+fEHNocZ+v1vLA4aOxJ
    ovp1JuXlAoGBAOWYNgKrlTfy5n0sKsNk+1RuL2jHJZJ3HMd0EIt7/fFQN3Fi08Hu
    jtntqD30Wj+DJK8b8Lrt66FruxyEJm5VhVmwkukrLR5ige2f6ftZnoFCmdyy+0zP
    dnPZSUe2H5ZPHa+qthJgHLn+al2P04tGh+1fGHC2PbP+e0Co+/ZRIOxrAoGBAMnN
    IEen9/FRsqvnDd36I8XnJGskVRTZNjylxBmbKcuMWm+gNhOI7gsCAcqzD4BYZjjW
    pLhrt/u9p+l4MOJy6OUUdM/okg12SnJEGryysOcVBcXyrvOfklWnANG4EAH5jt1N
    ftTb1XTxzvWVuR/WJK0B5MZNYM71cumBdUDtPi+nAoGAYmoIXMSnxb+8xNL10aOr
    h9ljQQp8NHgSQfyiSufvRk0YNuYh1vMnEIsqnsPrG2Zfhx/25GmvoxXGssaCorDN
    5FAn6QK06F1ZTD5L0Y3sv4OI6G1gAuC66ZWuL6sFhyyKkQ4f1WiVZ7SCa3CHQSAO
    i9VDaKz1bf4bXvAQcNj9v9kCgYACSOZCqW4vN0OUmqsXhkt9ZB6Pb/veno70pNPR
    jmYsvcwQU3oJQpWfXkhy6RAV3epaXmPDCsUsfns2M3wqNC7a2R5xdCqjKGGzZX4A
    AO3rz9se4J6Gd5oKijeCKFlWDGNHsibrdgm2pz42nZlY+O21X74dWKbt8O16I1MW
    hxkbJQKBgAXfuen/srVkJgPuqywUYag90VWCpHsuxdn+fZJa50SyZADr+RbiDfH2
    vek8Uo8ap8AEsv4Rfs9opUcUZevLp3g2741eOaidHVLm0l4iLIVl03otGOqvSzs+
    A3tFPEOxauXpzCt8f8eXsz0WQXAgIKW2h8zu5QHjomioU3i27mtE
    -----END RSA PRIVATE KEY-----
  rsa_public: ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC0/Ho+o3eJISydO2JvIgTLnZOtrxPl+fSvJfKDjoOLY0HB2eOjy2s2/2N6d9X9SGZ4+XnyVeNPjfBXw4IyXoqxhfIF16Azfk022iejgjiYssoUxH31M60OfqJhxo16dWEXdkKP1nac06VOt1zS5yEeooyvEuMJEJSsv3VR/7GKhMX3TVhEz5moLmVP3bIAvvoXio8X4urVC1R819QjDC86nlxwNks/GKPRi/IHO5tjJ72Eke7KNsm/vxHgkdX4vZaHNKhfdb/pavFXN5eoUaofz3hxw5oL/u2epI/pXyUhDp8Tb5wO6slykzcIlGCSd0YeO1TnljvViRx0uSxIy97N root@xenial-lxd
  rsa_certificate: ssh-rsa-cert-v01@openssh.com AAAAHHNzaC1yc2EtY2VydC12MDFAb3BlbnNzaC5jb20AAAAgMpgBP4Phn3L8I7Vqh7lmHKcOfIokEvSEbHDw83Y3JloAAAADAQABAAABAQC0/Ho+o3eJISydO2JvIgTLnZOtrxPl+fSvJfKDjoOLY0HB2eOjy2s2/2N6d9X9SGZ4+XnyVeNPjfBXw4IyXoqxhfIF16Azfk022iejgjiYssoUxH31M60OfqJhxo16dWEXdkKP1nac06VOt1zS5yEeooyvEuMJEJSsv3VR/7GKhMX3TVhEz5moLmVP3bIAvvoXio8X4urVC1R819QjDC86nlxwNks/GKPRi/IHO5tjJ72Eke7KNsm/vxHgkdX4vZaHNKhfdb/pavFXN5eoUaofz3hxw5oL/u2epI/pXyUhDp8Tb5wO6slykzcIlGCSd0YeO1TnljvViRx0uSxIy97NAAAAAAAAAAAAAAACAAAACnhlbmlhbC1seGQAAAAAAAAAAF+vVEIAAAAAYY83bgAAAAAAAAAAAAAAAAAAADMAAAALc3NoLWVkMjU1MTkAAAAgz4SlDwbq53ZrRsnS6ISdwxgFDRpnEX44K8jFmLpI9NAAAABTAAAAC3NzaC1lZDI1NTE5AAAAQMWpiRWKNMFvRX0g6OQOELMqDhtNBpkIN92IyO25qiY2oDSd1NyVme6XnGDFt8CS7z5NufV04doP4aacLOBbQww= root@xenial-lxd
  ed25519_private: |
    -----BEGIN OPENSSH PRIVATE KEY-----
    b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
    QyNTUxOQAAACDbnQGUruL42aVVsyHeaV5mYNTOhteXao0Nl5DVThJ2+QAAAJgwt+lcMLfp
    XAAAAAtzc2gtZWQyNTUxOQAAACDbnQGUruL42aVVsyHeaV5mYNTOhteXao0Nl5DVThJ2+Q
    AAAEDQlFZpz9q8+/YJHS9+jPAqy2ZT6cGEv8HTB6RZtTjd/dudAZSu4vjZpVWzId5pXmZg
    1M6G15dqjQ2XkNVOEnb5AAAAD3Jvb3RAeGVuaWFsLWx4ZAECAwQFBg==
    -----END OPENSSH PRIVATE KEY-----
  ed25519_public: ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINudAZSu4vjZpVWzId5pXmZg1M6G15dqjQ2XkNVOEnb5 root@xenial-lxd
  ed25519_certificate: ssh-ed25519-cert-v01@openssh.com AAAAIHNzaC1lZDI1NTE5LWNlcnQtdjAxQG9wZW5zc2guY29tAAAAIAGbMtat76PmaoqQ7B2lDvhnzE47psvMvmnPhz6f423ZAAAAINudAZSu4vjZpVWzId5pXmZg1M6G15dqjQ2XkNVOEnb5AAAAAAAAAAAAAAACAAAAA2x4ZAAAAAAAAAAAY+0LHAAAAABlzO1rAAAAAAAAAAAAAAAAAAABFwAAAAdzc2gtcnNhAAAAAwEAAQAAAQEAtPx6PqN3iSEsnTtibyIEy52Tra8T5fn0ryXyg46Di2NBwdnjo8trNv9jenfV/UhmePl58lXjT43wV8OCMl6KsYXyBdegM35NNtono4I4mLLKFMR99TOtDn6iYcaNenVhF3ZCj9Z2nNOlTrdc0uchHqKMrxLjCRCUrL91Uf+xioTF901YRM+ZqC5lT92yAL76F4qPF+Lq1QtUfNfUIwwvOp5ccDZLPxij0YvyBzubYye9hJHuyjbJv78R4JHV+L2WhzSoX3W/6WrxVzeXqFGqH894ccOaC/7tnqSP6V8lIQ6fE2+cDurJcpM3CJRgkndGHjtU55Y71YkcdLksSMvezQAAARQAAAAMcnNhLXNoYTItNTEyAAABAC8VDdaBkdt9jRW2Wh7A54rtbWyoafEtA8rud9UHgq3fSLFvWMBBe19/MJZXs+xWkdvSuG49ZeaEWi7ZO3SQaUbmXp2L5CH6TNnok3yo5QL2h01gP6+ydn98cA8lktvZt/+ihSqXpeSAg6S755W0zqlaeT5iyopSmNt4/wLh8FvgXR+TrAEe2EEXcPcLEXrBrPkjoLZ8j/pzLFJHHmlme/JcHPGMB7ksGG9nKr6ZViB3VPshdxP4iqpORv4Ro+UBUaS1AoHe0mZsccr7gKg7Xe6lhqHT2Fwlkk9B1zsWWUTjWU4TeG9FrJCjSAGCHLdHUszhCOsQHOOf9aR2095mbI8= root@xenial-lxd
  ecdsa_private: |
    -----BEGIN EC PRIVATE KEY-----
    MHcCAQEEIDuK+QFc1wmyJY8uDqQVa1qHte30Rk/fdLxGIBkwJAyOoAoGCCqGSM49
    AwEHoUQDQgAEWxLlO+TL8gL91eET9p/HFQbqR1A691AkJgZk3jY5mpZqxgX4vcgb
    7f/CtXuM6s2svcDJqAeXr6Wk8OJJcMxylA==
    -----END EC PRIVATE KEY-----
  ecdsa_public: ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBFsS5Tvky/IC/dXhE/afxxUG6kdQOvdQJCYGZN42OZqWasYF+L3IG+3/wrV7jOrNrL3AyagHl6+lpPDiSXDMcpQ= root@xenial-lxd
"""  # noqa


@pytest.mark.ci
@pytest.mark.user_data(USER_DATA)
class TestSshKeysProvided:
    @pytest.mark.parametrize(
        "config_path,expected_out",
        (
            (
                "/etc/ssh/ssh_host_rsa_key.pub",
                "AAAAB3NzaC1yc2EAAAADAQABAAABAQC0/Ho+o3eJISydO2JvIgT"
                "LnZOtrxPl+fSvJfKDjoOLY0HB2eOjy2s2/2N6d9X9SGZ4",
            ),
            (
                "/etc/ssh/ssh_host_rsa_key",
                "4DOkqNiUGl80Zp1RgZNohHUXlJMtAbrIlAVEk+mTmg7vjfyp2un"
                "RQvLZpMRdywBm",
            ),
            (
                "/etc/ssh/ssh_host_rsa_key-cert.pub",
                "AAAAHHNzaC1yc2EtY2VydC12MDFAb3BlbnNzaC5jb20AAAAgMpg"
                "BP4Phn3L8I7Vqh7lmHKcOfIokEvSEbHDw83Y3JloAAAAD",
            ),
            (
                "/etc/ssh/ssh_host_ecdsa_key.pub",
                "AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAAB"
                "BBFsS5Tvky/IC/dXhE/afxxU",
            ),
            (
                "/etc/ssh/ssh_host_ecdsa_key",
                "AwEHoUQDQgAEWxLlO+TL8gL91eET9p/HFQbqR1A691AkJgZk3jY"
                "5mpZqxgX4vcgb",
            ),
            (
                "/etc/ssh/ssh_host_ed25519_key.pub",
                "AAAAC3NzaC1lZDI1NTE5AAAAINudAZSu4vjZpVWzId5pXmZg1M6"
                "G15dqjQ2XkNVOEnb5",
            ),
            (
                "/etc/ssh/ssh_host_ed25519_key",
                "XAAAAAtzc2gtZWQyNTUxOQAAACDbnQGUruL42aVVsyHeaV5mYNT"
                "OhteXao0Nl5DVThJ2+Q",
            ),
        ),
    )
    def test_ssh_provided_keys(self, config_path, expected_out, class_client):
        out = class_client.read_from_file(config_path).strip()
        assert expected_out in out

    def test_sshd_config(self, class_client):
        expected_certs = (
            "HostCertificate /etc/ssh/ssh_host_rsa_key-cert.pub",
            "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub",
        )
        if CURRENT_RELEASE.series == "bionic":
            sshd_config_path = "/etc/ssh/sshd_config"
        else:
            sshd_config_path = "/etc/ssh/sshd_config.d/50-cloud-init.conf"
        sshd_config = class_client.read_from_file(sshd_config_path).strip()
        for expected_cert in expected_certs:
            assert expected_cert in sshd_config
