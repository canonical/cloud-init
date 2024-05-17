# Copyright (C) 2024 Aeza.net.
#
# Author: Egor Ternovoy <cofob@riseup.net>
#
# This file is part of cloud-init. See LICENSE file for license information.

import requests
import time
from requests.exceptions import HTTPError, RequestException

from cloudinit import util, dmi


def read_url(url, timeout=None, sec_between=1, retries=0):
    """
    A simplified HTTP GET request function with retry capability and specific handling for 404 errors.

    :param url: URL to request.
    :param timeout: Timeout in seconds for each request.
    :param sec_between: Seconds to wait between retries.
    :param retries: Number of retry attempts after the first failed request.
    """
    attempt = 0
    while attempt <= retries:
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()  # Will raise an HTTPError for bad responses
            return response
        except HTTPError as e:
            if e.response.status_code == 404:
                # Handle 404 specifically: exit the loop and return the error
                raise e
            if attempt == retries:
                # If it's the last attempt, re-raise the last exception for non-404 errors
                raise e
            # Wait before retrying if not a 404 error and retries are left
            time.sleep(sec_between)
            attempt += 1
        except RequestException as e:
            if attempt == retries:
                # If it's the last attempt, re-raise the last exception
                raise e
            # Wait before retrying if retries are left
            time.sleep(sec_between)
            attempt += 1

    # If retries are exhausted, raise an exception indicating the failure
    raise RequestException(f"Failed to retrieve data from {url} after {retries + 1} attempts.")


def read_metadata(url, timeout=2, sec_between=2, retries=30):
    """
    Read user data from URL or raise error.
    """
    response = read_url(
        url, timeout=timeout, sec_between=sec_between, retries=retries
    )
    if not response.ok:
        raise RuntimeError("unable to read metadata at %s" % url)
    return util.load_json(response.content.decode())


def read_data(url, timeout=2, sec_between=2, retries=30):
    """
    Read data from URL.
    """
    try:
        response = read_url(
            url, timeout=timeout, sec_between=sec_between, retries=retries
        )
        if not response.ok:
            raise RuntimeError("unable to read data at %s" % url)
        return response.content
    except HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise e


def format_url(url, system_uuid=None):
    if system_uuid is None:
        system_uuid = read_system_uuid()
    return url.format(id=system_uuid)


def read_system_uuid():
    return dmi.read_dmi_data("system-uuid")
