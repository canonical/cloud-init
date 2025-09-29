# Author: Jonas Keidel <jonas.keidel@hetzner.com>
# Author: Markus Schade <markus.schade@hetzner.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from typing import Optional, Tuple

from cloudinit import net, url_helper


def _skip_retry_on_empty_response(cause: url_helper.UrlError) -> bool:
    return cause.code != 204


def get_metadata(
    urls,
    max_wait=120,
    timeout=2,
    sleep_time=2,
) -> Tuple[Optional[str], bytes]:
    try:
        url, contents = url_helper.wait_for_url(
            urls=urls,
            max_wait=max_wait,
            timeout=timeout,
            sleep_time=sleep_time,
            # It is ok for userdata to not exist (that's why we are stopping if
            # HTTP code is 204) and just in that case returning an empty
            # string.
            exception_cb=_skip_retry_on_empty_response,
        )
        if not url:
            raise RuntimeError("No data received from urls: '%s':" % urls)
        return url, contents
    except url_helper.UrlError as e:
        if e.code == 204:
            return e.url, b""
        raise


def get_interface_name_from_mac(mac: str) -> Optional[str]:
    mac_to_iface = net.get_interfaces_by_mac()
    return mac_to_iface.get(mac.lower())
