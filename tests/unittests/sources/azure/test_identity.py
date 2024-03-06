# This file is part of cloud-init. See LICENSE file for license information.

from unittest import mock

import pytest

from cloudinit.sources.azure import identity


@pytest.fixture(autouse=True)
def mock_read_dmi_data():
    with mock.patch.object(
        identity.dmi, "read_dmi_data", return_value=None
    ) as m:
        yield m


@pytest.fixture(autouse=True)
def mock_os_path_exists():
    with mock.patch.object(identity.os.path, "exists") as m:
        yield m


class TestByteSwapSystemUuid:
    @pytest.mark.parametrize(
        "system_uuid,swapped_uuid",
        [
            (
                "527c2691-029f-fe4c-b1f4-a4da7ebac2cf",
                "91267c52-9f02-4cfe-b1f4-a4da7ebac2cf",
            ),
            (
                "527C2691-029F-FE4C-B1F4-A4DA7EBAC2CD",
                "91267c52-9f02-4cfe-b1f4-a4da7ebac2cd",
            ),
        ],
    )
    def test_values(self, system_uuid, swapped_uuid):
        assert identity.byte_swap_system_uuid(system_uuid) == swapped_uuid

    @pytest.mark.parametrize(
        "system_uuid",
        [
            "",
            "g",
            "91267c52-9f02-4cfe-b1f4-a4da7ebac2c",
            "91267c52-9f02-4cfe-b1f4-a4da7ebac2ccc",
            "-----",
        ],
    )
    def test_errors(self, system_uuid):
        with pytest.raises(ValueError) as exc_info:
            identity.byte_swap_system_uuid(system_uuid)

        assert exc_info.value.args[0] == "badly formed hexadecimal UUID string"


class TestConvertSystemUuidToVmId:
    def test_gen1(self, monkeypatch):
        system_uuid = "527c2691-029f-fe4c-b1f4-a4da7ebac2cf"
        monkeypatch.setattr(identity, "is_vm_gen1", lambda: True)

        swapped_uuid = "91267c52-9f02-4cfe-b1f4-a4da7ebac2cf"
        assert (
            identity.convert_system_uuid_to_vm_id(system_uuid) == swapped_uuid
        )

    def test_gen2(self, monkeypatch):
        system_uuid = "527c2691-029f-fe4c-b1f4-a4da7ebac2cf"
        monkeypatch.setattr(identity, "is_vm_gen1", lambda: False)

        assert (
            identity.convert_system_uuid_to_vm_id(system_uuid) == system_uuid
        )


class TestIsVmGen1:
    def test_gen1(self, mock_os_path_exists) -> None:
        mock_os_path_exists.side_effect = lambda _: False

        assert identity.is_vm_gen1() is True

    def test_gen2_freebsd(self, mock_os_path_exists) -> None:
        mock_os_path_exists.side_effect = lambda x: x == "/dev/efi"

        assert identity.is_vm_gen1() is False

    def test_gen2_linux(self, mock_os_path_exists) -> None:
        mock_os_path_exists.side_effect = lambda x: x == "/sys/firmware/efi"

        assert identity.is_vm_gen1() is False


class TestQuerySystemUuid:
    @pytest.mark.parametrize(
        "system_uuid",
        [
            "527c2691-029f-fe4c-b1f4-a4da7ebac2cf",
            "527C2691-029F-FE4C-B1F4-A4DA7EBAC2CF",
        ],
    )
    def test_values(self, mock_read_dmi_data, system_uuid):
        mock_read_dmi_data.return_value = system_uuid

        assert identity.query_system_uuid() == system_uuid.lower()
        assert mock_read_dmi_data.mock_calls == [mock.call("system-uuid")]

    def test_errors(self, mock_read_dmi_data):
        mock_read_dmi_data.return_value = None

        with pytest.raises(RuntimeError) as exc_info:
            identity.query_system_uuid()

        assert exc_info.value.args[0] == "failed to read system-uuid"


class TestQueryVmId:
    def test_gen1(self, monkeypatch):
        system_uuid = "527c2691-029f-fe4c-b1f4-a4da7ebac2cf"
        swapped_uuid = "91267c52-9f02-4cfe-b1f4-a4da7ebac2cf"
        monkeypatch.setattr(identity, "query_system_uuid", lambda: system_uuid)
        monkeypatch.setattr(identity, "is_vm_gen1", lambda: True)

        assert identity.query_vm_id() == swapped_uuid

    def test_gen2(self, monkeypatch):
        system_uuid = "527c2691-029f-fe4c-b1f4-a4da7ebac2cf"
        monkeypatch.setattr(identity, "query_system_uuid", lambda: system_uuid)
        monkeypatch.setattr(identity, "is_vm_gen1", lambda: False)

        assert identity.query_vm_id() == system_uuid


class TestChassisAssetTag:
    def test_true_azure_cloud(self, caplog, mock_read_dmi_data):
        mock_read_dmi_data.return_value = (
            identity.ChassisAssetTag.AZURE_CLOUD.value
        )

        asset_tag = identity.ChassisAssetTag.query_system()

        assert asset_tag == identity.ChassisAssetTag.AZURE_CLOUD
        assert caplog.record_tuples == [
            (
                "cloudinit.sources.azure.identity",
                10,
                "Azure chassis asset tag: "
                "'7783-7084-3265-9085-8269-3286-77' (AZURE_CLOUD)",
            )
        ]

    @pytest.mark.parametrize("tag", [None, "", "notazure"])
    def test_false_on_nonazure_chassis(self, caplog, mock_read_dmi_data, tag):
        mock_read_dmi_data.return_value = tag

        asset_tag = identity.ChassisAssetTag.query_system()

        assert asset_tag is None
        assert caplog.record_tuples == [
            (
                "cloudinit.sources.azure.identity",
                10,
                "Non-Azure chassis asset tag: %r" % tag,
            )
        ]
