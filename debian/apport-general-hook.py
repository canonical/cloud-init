"""General Apport hook for all reports that are using cloud-init."""

from cloudinit.apport import general_add_info


def add_info(report, ui) -> None:
    """Entry point for Apport.

    Add a subset of non-sensitive cloud-init data from
    /run/cloud/instance-data.json that will be helpful for debugging.
    """
    general_add_info(report, ui)
