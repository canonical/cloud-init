# Author: Jonas Keidel <jonas.keidel@hetzner.com>
# Author: Markus Schade <markus.schade@hetzner.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import url_helper, net
from typing import Optional


def skip_retry_on_empty_response(cause: url_helper.UrlError) -> bool:
    """Returns False if cause.code is 200 and 'Content-Length' is '0'."""
    return not (
        cause.code == 200 and cause.headers.get("Content-Length") == "0"
    )


def get_metadata(
    urls,
    max_wait=120,
    sec_between=2,
    retries=30,
    timeout=2,
    sleep_time=2,
    exception_cb=None,
) -> tuple[str, bytes]:
    try:
        if not exception_cb:
            # It is ok for userdata to not exist (thats why we are stopping if
            # response is empty) and just in that case returning an empty
            # string.
            exception_cb = skip_retry_on_empty_response
        url, contents = url_helper.wait_for_url(
            urls=urls,
            max_wait=max_wait,
            timeout=timeout,
            sleep_time=sleep_time,
            exception_cb=exception_cb,
        )
        return url, contents
    except url_helper.UrlError as e:
        if e.code == 200 and e.headers.get("Content-Length") == "0":
            return e.url, b""


def get_interface_name_from_mac(mac: str) -> Optional[str]:
    mac_to_iface = net.get_interfaces_by_mac()
    return mac_to_iface.get(mac.lower())
