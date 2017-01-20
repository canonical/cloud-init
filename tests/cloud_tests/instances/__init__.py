# This file is part of cloud-init. See LICENSE file for license information.


def get_instance(snapshot, *args, **kwargs):
    """
    get instance from snapshot
    """
    return snapshot.launch(*args, **kwargs)

# vi: ts=4 expandtab
