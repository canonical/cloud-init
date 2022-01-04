# Author: Jonas Keidel <jonas.keidel@hetzner.com>
# Author: Markus Schade <markus.schade@hetzner.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import base64
import binascii

from cloudinit import url_helper, util


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


def maybe_b64decode(data: bytes) -> bytes:
    """base64 decode data

    If data is base64 encoded bytes, return b64decode(data).
    If not, return data unmodified.

    @param data: data as bytes. TypeError is raised if not bytes.
    """
    if not isinstance(data, bytes):
        raise TypeError("data is '%s', expected bytes" % type(data))
    try:
        return base64.b64decode(data, validate=True)
    except binascii.Error:
        return data
