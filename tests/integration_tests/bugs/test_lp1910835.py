"""Integration test for LP: #1910835.

If users do not provide an SSH key and instead ask Azure to generate a key for
them, the key material available in the IMDS may include CRLF sequences.  Prior
to e56b55452549cb037da0a4165154ffa494e9678a, the Azure datasource handled keys
via a certificate, the tooling for which removed these sequences.  This test
ensures that cloud-init does not regress support for this Azure behaviour.

This test provides the SSH key configured for tests to the instance in two
ways: firstly, with CRLFs to mimic the generated keys, via the Azure API;
secondly, as user-data in unmodified form.  This means that even on systems
which exhibit the bug fetching the platform's metadata, we can SSH into the SUT
to confirm this (instead of having to assert SSH failure; there are lots of
reasons SSH might fail).

Once SSH'd in, we check that the two keys in .ssh/authorized_keys have the same
material: if the Azure datasource has removed the CRLFs correctly, then they
will match.
"""
import pytest

USER_DATA_TMPL = """\
#cloud-config
ssh_authorized_keys:
    - {}"""


@pytest.mark.azure
def test_crlf_in_azure_metadata_ssh_keys(session_cloud, setup_image):
    authorized_keys_path = "/home/{}/.ssh/authorized_keys".format(
        session_cloud.cloud_instance.username
    )
    # Pass in user-data to allow us to access the instance when the normal
    # path fails
    key_data = session_cloud.cloud_instance.key_pair.public_key_content
    user_data = USER_DATA_TMPL.format(key_data)
    # Throw a CRLF into the otherwise good key data, to emulate Azure's
    # behaviour for generated keys
    key_data = key_data[:20] + "\r\n" + key_data[20:]
    vm_params = {
        "os_profile": {
            "linux_configuration": {
                "ssh": {
                    "public_keys": [
                        {"path": authorized_keys_path, "key_data": key_data}
                    ]
                }
            }
        }
    }
    with session_cloud.launch(
        launch_kwargs={"vm_params": vm_params, "user_data": user_data}
    ) as client:
        authorized_keys = (
            client.read_from_file(authorized_keys_path).strip().splitlines()
        )
        # We expect one key from the cloud, one from user-data
        assert 2 == len(authorized_keys)
        # And those two keys should be the same, except for a possible key
        # comment, which Azure strips out
        assert (
            authorized_keys[0].rsplit(" ")[:2]
            == authorized_keys[1].split(" ")[:2]
        )
