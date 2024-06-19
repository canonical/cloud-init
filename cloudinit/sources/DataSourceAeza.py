# Copyright (C) 2024 Aeza.net.
#
# Author: Egor Ternovoy <cofob@riseup.net>
#
# This file is part of cloud-init. See LICENSE file for license information.

import time

import requests
from requests.exceptions import HTTPError, RequestException

from cloudinit import sources, dmi, util

BASE_URL_V1 = "http://77.221.156.49/v1/cloudinit"

BUILTIN_DS_CONFIG = {
    "metadata_url": BASE_URL_V1 + "/{id}/meta-data",
    "userdata_url": BASE_URL_V1 + "/{id}/user-data",
    "vendordata_url": BASE_URL_V1 + "/{id}/vendor-data",
}


def read_url(url, timeout_seconds=None, max_wait_seconds=None, sec_between_retries=1, retries=0):
    """
    A simplified HTTP GET request function with retry capability and specific handling for 404 errors.

    :param url: URL to request.
    :param timeout_seconds: Timeout in seconds for each request.
    :param max_wait_seconds: Timeout for whole request process.
    :param sec_between_retries: Seconds to wait between retries.
    :param retries: Number of retry attempts after the first failed request.
    """
    attempt = 0
    start = time.time()
    while attempt <= retries:
        try:
            response = requests.get(url, timeout=timeout_seconds)
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
            time.sleep(sec_between_retries)
            attempt += 1
        except RequestException as e:
            if attempt == retries:
                # If it's the last attempt, re-raise the last exception
                raise e
            # Wait before retrying if retries are left
            time.sleep(sec_between_retries)
            attempt += 1
        # If max_wait timeout is enabled check for max wait timeout
        if max_wait_seconds is not None:
            if start + max_wait_seconds < time.time():
                raise RequestException(
                    f"Failed to retrieve data from {url} after {retries + 1} attempts because of max wait timeout."
                )

    # If retries are exhausted, raise an exception indicating the failure
    raise RequestException(f"Failed to retrieve data from {url} after {retries + 1} attempts.")


def read_metadata(url, timeout_seconds=2, max_wait_seconds=120, sec_between_retries=2, retries=30):
    """
    Read user data from URL or raise error.
    """
    response = read_url(
        url,
        timeout_seconds=timeout_seconds,
        max_wait_seconds=max_wait_seconds,
        sec_between_retries=sec_between_retries,
        retries=retries,
    )
    if not response.ok:
        raise RuntimeError("unable to read metadata at %s" % url)
    return util.load_json(response.content.decode())


def read_data(url, timeout_seconds=2, max_wait_seconds=120, sec_between_retries=2, retries=30):
    """
    Read data from URL.
    """
    try:
        response = read_url(
            url,
            timeout_seconds=timeout_seconds,
            max_wait_seconds=max_wait_seconds,
            sec_between_retries=sec_between_retries,
            retries=retries,
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
        system_uuid = dmi.read_dmi_data("system-uuid")
    return url.format(id=system_uuid)


class DataSourceAeza(sources.DataSource):

    dsname = "Aeza"

    def __init__(self, sys_cfg, distro, paths, ud_proc=None):
        super().__init__(sys_cfg, distro, paths, ud_proc)

        self.ds_cfg = util.mergemanydict([self.ds_cfg, BUILTIN_DS_CONFIG])

        url_params = self.get_url_params()
        self.timeout_seconds = url_params.timeout_seconds
        self.max_wait_seconds = url_params.max_wait_seconds
        self.retries = url_params.num_retries
        self.sec_between_retries = url_params.sec_between_retries

        self.metadata_address = self.ds_cfg["metadata_url"]
        self.userdata_address = self.ds_cfg["userdata_url"]
        self.vendordata_address = self.ds_cfg["vendordata_url"]

    @staticmethod
    def ds_detect():
        return dmi.read_dmi_data("system-manufacturer") == "Aeza"

    def _get_data(self):
        system_uuid = dmi.read_dmi_data("system-uuid")

        md = read_metadata(
            format_url(self.metadata_address, system_uuid),
            timeout_seconds=self.timeout_seconds,
            max_wait_seconds=self.max_wait_seconds,
            sec_between_retries=self.sec_between_retries,
            retries=self.retries,
        )
        ud = read_data(
            format_url(self.userdata_address, system_uuid),
            timeout_seconds=self.timeout_seconds,
            max_wait_seconds=self.max_wait_seconds,
            sec_between_retries=self.sec_between_retries,
            retries=self.retries,
        )
        vd = read_data(
            format_url(self.vendordata_address, system_uuid),
            timeout_seconds=self.timeout_seconds,
            max_wait_seconds=self.max_wait_seconds,
            sec_between_retries=self.sec_between_retries,
            retries=self.retries,
        )

        self.metadata = md
        self.userdata_raw = ud
        self.vendordata_raw = vd

        return True


datasources = [
    (DataSourceAeza, (sources.DEP_NETWORK, sources.DEP_FILESYSTEM)),
]


def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
