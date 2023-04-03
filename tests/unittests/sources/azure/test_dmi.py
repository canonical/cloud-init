# This file is part of cloud-init. See LICENSE file for license information.


import pytest

from cloudinit.sources.azure import dmi


@pytest.mark.parametrize(
    "product_uuid,vm_id",
    [
        (None, None),
        (
            "527c2691-029f-fe4c-b1f4-a4da7ebac2cf",
            "91267c52-9f02-4cfe-b1f4-a4da7ebac2cf",
        ),
        (
            "garbage-in-garbage-out",
            None,
        ),
    ],
)
def test_query_vm_id(monkeypatch, product_uuid, vm_id):
    monkeypatch.setattr(dmi.dmi, "read_dmi_data", lambda _: product_uuid)

    assert dmi.query_vm_id() == vm_id
