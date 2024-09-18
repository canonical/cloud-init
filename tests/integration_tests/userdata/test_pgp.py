"""Test PGP signed and encrypted userdata."""

import pytest

from cloudinit import subp
from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.util import verify_clean_boot

USER_DATA = """\
#cloud-config
bootcmd:
 - touch /var/tmp/{0}
"""


@pytest.fixture(scope="module")
def gpg_dir(tmp_path_factory):
    yield tmp_path_factory.mktemp("gpg_dir")


@pytest.fixture(scope="module")
def public_key(gpg_dir):
    subp.subp(
        [
            "gpg",
            "--homedir",
            str(gpg_dir),
            "--quick-generate-key",
            "--batch",
            # "loopback",
            "--passphrase",
            "",
            "signing_user",
        ]
    )
    yield subp.subp(
        [
            "gpg",
            "--homedir",
            str(gpg_dir),
            "--export",
            "--armor",
            "signing_user",
        ]
    ).stdout


@pytest.fixture(scope="module")
def private_key(gpg_dir):
    subp.subp(
        [
            "gpg",
            "--homedir",
            str(gpg_dir),
            "--quick-generate-key",
            "--batch",
            "--passphrase",
            "",
            "encrypting_user",
        ]
    )
    yield subp.subp(
        [
            "gpg",
            "--homedir",
            str(gpg_dir),
            "--batch",
            "--export-secret-keys",
            "--armor",
            "encrypting_user",
        ]
    ).stdout


@pytest.fixture(scope="module")
def signed_and_encrypted_userdata(gpg_dir, public_key, private_key):
    return subp.subp(
        [
            "gpg",
            "--homedir",
            str(gpg_dir),
            "--batch",
            "--sign",
            "--local-user",
            "signing_user",
            "--encrypt",
            "--recipient",
            "encrypting_user",
            "--armor",
        ],
        data=USER_DATA.format("signed_and_encrypted"),
    ).stdout


@pytest.fixture(scope="module")
def signed_userdata(gpg_dir, public_key):
    return subp.subp(
        [
            "gpg",
            "--homedir",
            str(gpg_dir),
            "--batch",
            "--sign",
            "--local-user",
            "signing_user",
            "--armor",
        ],
        data=USER_DATA.format("signed"),
    ).stdout


@pytest.fixture(scope="module")
def encrypted_userdata(gpg_dir, private_key):
    return subp.subp(
        [
            "gpg",
            "--homedir",
            str(gpg_dir),
            "--batch",
            "--encrypt",
            "--recipient",
            "encrypting_user",
            "--armor",
        ],
        data=USER_DATA.format("encrypted"),
    ).stdout


@pytest.fixture(scope="module")
def valid_keys_image(
    public_key,
    private_key,
    session_cloud: IntegrationCloud,
):
    with session_cloud.launch() as client:
        client.execute("mkdir /etc/cloud/keys")
        client.write_to_file("/etc/cloud/keys/pub_key", public_key)
        client.write_to_file("/etc/cloud/keys/priv_key", private_key)
        client.execute("cloud-init clean --logs")
        image_id = client.snapshot()
        yield image_id
        client.cloud.cloud_instance.delete_image(image_id)


@pytest.fixture(scope="module")
def valid_pub_key_image(
    public_key,
    session_cloud: IntegrationCloud,
):
    with session_cloud.launch() as client:
        client.execute("mkdir /etc/cloud/keys")
        client.write_to_file("/etc/cloud/keys/pub_key", public_key)
        client.execute("cloud-init clean --logs")
        image_id = client.snapshot()
        yield image_id
        client.cloud.cloud_instance.delete_image(image_id)


@pytest.fixture(scope="module")
def valid_priv_key_image(
    private_key,
    session_cloud: IntegrationCloud,
):
    with session_cloud.launch() as client:
        client.execute("mkdir /etc/cloud/keys")
        client.write_to_file("/etc/cloud/keys/priv_key", private_key)
        client.execute("cloud-init clean --logs")
        image_id = client.snapshot()
        yield image_id
        client.cloud.cloud_instance.delete_image(image_id)


@pytest.fixture
def pgp_client(session_cloud: IntegrationCloud, request):
    user_data_fixture, image_id_fixture = request.param
    user_data = request.getfixturevalue(user_data_fixture)
    launch_kwargs = {"image_id": request.getfixturevalue(image_id_fixture)}
    with session_cloud.launch(
        user_data=user_data, launch_kwargs=launch_kwargs
    ) as client:
        yield client


def _invalidate_key(client, key_path):
    pub_key = client.read_from_file(key_path)
    midde_index = len(pub_key) // 2
    bad_pub_key = f"{pub_key[:midde_index]}a{pub_key[midde_index:]}"
    client.write_to_file(key_path, bad_pub_key)


@pytest.mark.parametrize(
    "pgp_client",
    [("signed_and_encrypted_userdata", "valid_keys_image")],
    indirect=True,
)
def test_signed_and_encrypted(pgp_client: IntegrationInstance):
    client = pgp_client
    assert client.execute("test -f /var/tmp/signed_and_encrypted")
    verify_clean_boot(client)

    # Invalidate our public key and ensure we fail
    client.execute("cp /etc/cloud/keys/pub_key /var/tmp/pub_key")
    _invalidate_key(client, "/etc/cloud/keys/pub_key")
    client.execute("cloud-init clean --logs")
    client.execute("rm /var/tmp/signed_and_encrypted")
    client.restart()
    assert not client.execute("test -f /var/tmp/signed_and_encrypted")
    result = client.execute("cloud-init status --format=json")
    assert result.failed
    assert "Failed decrypting user data" in result.stdout

    # Restore the public key, invalidate the private key, and ensure we fail
    client.execute("cp /var/tmp/pub_key /etc/cloud/keys/pub_key")
    client.execute("cp /etc/cloud/keys/priv_key /var/tmp/priv_key")
    _invalidate_key(client, "/etc/cloud/keys/priv_key")
    client.execute("cloud-init clean --logs")
    client.execute("rm /var/tmp/signed_and_encrypted")
    client.restart()
    assert not client.execute("test -f /var/tmp/signed_and_encrypted")
    result = client.execute("cloud-init status --format=json")
    assert result.failed
    assert "Failed decrypting user data" in result.stdout


@pytest.mark.parametrize(
    "pgp_client",
    [("encrypted_userdata", "valid_priv_key_image")],
    indirect=True,
)
def test_encrypted(pgp_client: IntegrationInstance):
    client = pgp_client
    assert client.execute("test -f /var/tmp/encrypted")
    verify_clean_boot(client)

    # Invalidate our private key and ensure we fail
    _invalidate_key(client, "/etc/cloud/keys/priv_key")
    client.execute("cloud-init clean --logs")
    client.execute("rm /var/tmp/encrypted")
    client.restart()
    assert not client.execute("test -f /var/tmp/encrypted")
    result = client.execute("cloud-init status --format=json")
    assert result.failed
    assert "Failed decrypting user data" in result.stdout


@pytest.mark.parametrize(
    "pgp_client",
    [("signed_userdata", "valid_pub_key_image")],
    indirect=True,
)
def test_signed(pgp_client: IntegrationInstance):
    client = pgp_client
    assert client.execute("test -f /var/tmp/signed")
    verify_clean_boot(client)

    # Invalidate our public key and ensure we fail
    _invalidate_key(client, "/etc/cloud/keys/pub_key")
    client.execute("cloud-init clean --logs")
    client.execute("rm /var/tmp/signed")
    client.restart()
    assert not client.execute("test -f /var/tmp/signed")
    result = client.execute("cloud-init status --format=json")
    assert result.failed
    assert "Failed decrypting user data" in result.stdout


@pytest.fixture
def lxd_pgp_client(session_cloud: IntegrationCloud, request):
    user_data_fixture, image_id_fixture = request.param
    user_data = request.getfixturevalue(user_data_fixture)
    launch_kwargs = {
        "execute_via_ssh": False,
        "username": "root",
    }
    if image_id_fixture:
        launch_kwargs["image_id"] = request.getfixturevalue(image_id_fixture)

    with session_cloud.launch(
        user_data=user_data, launch_kwargs=launch_kwargs
    ) as client:
        yield client


@pytest.mark.skipif(
    PLATFORM not in ["lxd_container", "lxd_vm"],
    reason=(
        "failed user data means no ssh or 'ubuntu' user creation, "
        "so we need special LXD options"
    ),
)
@pytest.mark.parametrize(
    "lxd_pgp_client",
    [
        pytest.param(
            ("encrypted_userdata", "valid_pub_key_image"),
            id="encrypted_with_no_priv_key",
        ),
        pytest.param(
            ("signed_userdata", "valid_priv_key_image"),
            id="signed_with_no_pub_key",
        ),
        pytest.param(
            ("signed_and_encrypted_userdata", None),
            id="signed_and_encrypted_with_no_keys",
        ),
    ],
    indirect=True,
)
def test_unparseable_userdata(
    lxd_pgp_client: IntegrationInstance,
):
    result = lxd_pgp_client.execute("cloud-init status --format=json")
    assert result.failed
    assert "Failed decrypting user data" in result.stdout


@pytest.mark.user_data(USER_DATA.format("no"))
def test_signature_required(client: IntegrationInstance):
    client.write_to_file(
        "/etc/cloud/cloud.cfg.d/99_pgp.cfg",
        "user_data:\n  require_signature: true",
    )
    client.execute("cloud-init clean --logs")
    client.restart()

    result = client.execute("cloud-init status --format=json")
    assert result.failed
    assert (
        "'require_signature' was set true in cloud-init's base configuration, "
        "but content type is text/cloud-config"
    ) in result.stdout


@pytest.mark.parametrize(
    "pgp_client", [("encrypted_userdata", "valid_keys_image")], indirect=True
)
def test_encrypted_message_but_required_signature(
    pgp_client: IntegrationInstance,
):
    """Ensure fail if we require signature but only have encrypted message."""
    client = pgp_client
    assert client.execute("test -f /var/tmp/encrypted")
    verify_clean_boot(client)

    client.write_to_file(
        "/etc/cloud/cloud.cfg.d/99_pgp.cfg",
        "user_data:\n  require_signature: true",
    )
    client.execute("cloud-init clean --logs")
    client.restart()

    result = client.execute("cloud-init status --format=json")
    assert result.failed
    assert "Signature verification failed" in result.stdout
