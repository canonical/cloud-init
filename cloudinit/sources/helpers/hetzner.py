# Author: Jonas Keidel <jonas.keidel@hetzner.com>
# Author: Markus Schade <markus.schade@hetzner.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import url_helper, util


def read_networks(url, timeout=2, sec_between=2, retries=30):
    response = url_helper.readurl(
        url, timeout=timeout, sec_between=sec_between, retries=retries
    )
    if not response.ok():
        raise RuntimeError("unable to read networks at %s" % url)

    parsed = util.load_yaml(response.contents.decode(), default=None, allowed=(list,))

    if not isinstance(parsed, list):
        raise ValueError("Expected a list of network entries in metadata")

    return {
        "private_networks": {
            entry["network_name"]: {
                k: v for k, v in entry.items()
            }
            for entry in parsed
        }
    }

def read_metadata(url, timeout=2, sec_between=2, retries=30):
    response = url_helper.readurl(
        url, timeout=timeout, sec_between=sec_between, retries=retries
    )
    if not response.ok():
        raise RuntimeError("unable to read metadata at %s" % url)
    return util.load_yaml(response.contents.decode())


def read_userdata(url, timeout=2, sec_between=2, retries=30):
    response = url_helper.readurl(
        url, timeout=timeout, sec_between=sec_between, retries=retries
    )
    if not response.ok():
        raise RuntimeError("unable to read userdata at %s" % url)
    return response.contents
