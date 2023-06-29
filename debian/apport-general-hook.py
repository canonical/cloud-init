"""General Apport hook for all reports that are using cloud-init."""

import json
import logging
from typing import Dict


def _get_azure_data(ds_data) -> Dict[str, str]:
    compute = ds_data.get("meta_data", {}).get("imds", {}).get("compute")
    if not compute:
        return {}
    name_to_report_map = {
        "publisher": "ImagePublisher",
        "offer": "ImageOffer",
        "sku": "ImageSKU",
        "version": "ImageVersion",
        "vmSize": "VMSize",
    }
    azure_data = {}
    for src_key, report_key_name in name_to_report_map.items():
        azure_data[report_key_name] = compute[src_key]
    return azure_data


def _get_ec2_data(ds_data) -> Dict[str, str]:
    document = (
        ds_data.get("dynamic", {}).get("instance-identity", {}).get("document")
    )
    if not document:
        return {}
    wanted_keys = {
        "architecture",
        "billingProducts",
        "imageId",
        "instanceType",
        "region",
    }
    return {
        key: value for key, value in document.items() if key in wanted_keys
    }


PLATFORM_SPECIFIC_INFO = {"azure": _get_azure_data, "ec2": _get_ec2_data}


def add_datasource_specific_info(report, platform: str, ds_data) -> None:
    """Add datasoure specific information from the ds dictionary.

    ds_data contains the "ds" entry from data from
    /run/cloud/instance-data.json.
    """
    platform_info = PLATFORM_SPECIFIC_INFO.get(platform)
    if not platform_info:
        return
    retrieved_data = platform_info(ds_data)
    for key, value in retrieved_data.items():
        if not value:
            continue
        report[platform.capitalize() + key.capitalize()] = value


def add_info(report, ui) -> None:
    """Entry point for Apport.

    Add a subset of non-sensitive cloud-init data from
    /run/cloud/instance-data.json that will be helpful for debugging.
    """
    try:
        with open("/run/cloud-init/instance-data.json", "r") as fopen:
            instance_data = json.load(fopen)
    except FileNotFoundError:
        logging.getLogger().warning(
            "cloud-init run data not found on system. "
            "Unable to add cloud-specific data."
        )
        return

    v1 = instance_data.get("v1")
    if not v1:
        logging.getLogger().warning(
            "instance-data.json lacks 'v1' metadata. Present keys: %s",
            sorted(instance_data.keys()),
        )
        return

    for key, report_key in {
        "cloud_id": "CloudID",
        "cloud_name": "CloudName",
        "machine": "CloudArchitecture",
        "platform": "CloudPlatform",
        "region": "CloudRegion",
        "subplatform": "CloudSubPlatform",
    }.items():
        value = v1.get(key)
        if value:
            report[report_key] = value

    add_datasource_specific_info(
        report, v1["platform"], instance_data.get("ds")
    )
