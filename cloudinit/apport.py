# Copyright (C) 2017 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Cloud-init apport interface"""

import os

from cloudinit.cmd.devel import read_cfg_paths
from cloudinit.cmd.devel.logs import (
    INSTALLER_APPORT_FILES,
    INSTALLER_APPORT_SENSITIVE_FILES,
)

try:
    from apport.hookutils import (
        attach_file,
        attach_file_if_exists,
        attach_root_command_outputs,
        root_command_output,
    )

    has_apport = True
except ImportError:
    has_apport = False


KNOWN_CLOUD_NAMES = [
    "AliYun",
    "AltCloud",
    "Amazon - Ec2",
    "Azure",
    "Bigstep",
    "Brightbox",
    "CloudSigma",
    "CloudStack",
    "DigitalOcean",
    "E24Cloud",
    "GCE - Google Compute Engine",
    "Huawei Cloud",
    "Exoscale",
    "Hetzner Cloud",
    "NWCS",
    "IBM - (aka SoftLayer or BlueMix)",
    "LXD",
    "MAAS",
    "NoCloud",
    "OpenNebula",
    "OpenStack",
    "Oracle",
    "OVF",
    "RbxCloud - (HyperOne, Rootbox, Rubikon)",
    "OpenTelekomCloud",
    "SAP Converged Cloud",
    "Scaleway",
    "SmartOS",
    "UpCloud",
    "VMware",
    "Vultr",
    "ZStack",
    "Outscale",
    "Other",
]

# Potentially clear text collected logs
CLOUDINIT_LOG = "/var/log/cloud-init.log"
CLOUDINIT_OUTPUT_LOG = "/var/log/cloud-init-output.log"


def _get_user_data_file() -> str:
    paths = read_cfg_paths()
    return paths.get_ipath_cur("userdata_raw")


def attach_cloud_init_logs(report, ui=None):
    """Attach cloud-init logs and tarfile from 'cloud-init collect-logs'."""
    attach_root_command_outputs(
        report,
        {
            "cloud-init-log-warnings": (
                'egrep -i "warn|error" /var/log/cloud-init.log'
            ),
            "cloud-init-output.log.txt": "cat /var/log/cloud-init-output.log",
        },
    )
    root_command_output(
        ["cloud-init", "collect-logs", "-t", "/tmp/cloud-init-logs.tgz"]
    )
    attach_file(report, "/tmp/cloud-init-logs.tgz", "logs.tgz")


def attach_hwinfo(report, ui=None):
    """Optionally attach hardware info from lshw."""
    prompt = (
        "Your device details (lshw) may be useful to developers when"
        " addressing this bug, but gathering it requires admin privileges."
        " Would you like to include this info?"
    )
    if ui and ui.yesno(prompt):
        attach_root_command_outputs(report, {"lshw.txt": "lshw"})


def attach_cloud_info(report, ui=None):
    """Prompt for cloud details if available."""
    if ui:
        prompt = "Is this machine running in a cloud environment?"
        response = ui.yesno(prompt)
        if response is None:
            raise StopIteration  # User cancelled
        if response:
            prompt = (
                "Please select the cloud vendor or environment in which"
                " this instance is running"
            )
            response = ui.choice(prompt, KNOWN_CLOUD_NAMES)
            if response:
                report["CloudName"] = KNOWN_CLOUD_NAMES[response[0]]
            else:
                report["CloudName"] = "None"


def attach_installer_files(report, ui=None):
    """Attach any subiquity installer logs config.

    To support decoupling apport integration from installer config/logs,
    we eventually want to either source this function or APPORT_FILES
    attribute from subiquity  and/or ubuntu-desktop-installer package-hooks
    python modules.
    """
    for apport_file in INSTALLER_APPORT_FILES:
        realpath = os.path.realpath(apport_file.path)
        attach_file_if_exists(report, realpath, apport_file.label)


def attach_user_data(report, ui=None):
    """Optionally provide user-data if desired."""
    if ui:
        user_data_file = _get_user_data_file()
        prompt = (
            "Your user-data, cloud-config or autoinstall files can optionally "
            " be provided from {0} and could be useful to developers when"
            " addressing this bug. Do you wish to attach user-data to this"
            " bug?".format(user_data_file)
        )
        response = ui.yesno(prompt)
        if response is None:
            raise StopIteration  # User cancelled
        if response:
            realpath = os.path.realpath(user_data_file)
            attach_file(report, realpath, "user_data.txt")
            for apport_file in INSTALLER_APPORT_SENSITIVE_FILES:
                realpath = os.path.realpath(apport_file.path)
                attach_file_if_exists(report, realpath, apport_file.label)


def add_bug_tags(report):
    """Add any appropriate tags to the bug."""
    new_tags = []
    if report.get("CurtinError"):
        new_tags.append("curtin")
    if report.get("SubiquityLog"):
        new_tags.append("subiquity")
    if "JournalErrors" in report.keys():
        errors = report["JournalErrors"]
        if "Breaking ordering cycle" in errors:
            new_tags.append("systemd-ordering")
    if report.get("UdiLog"):
        new_tags.append("ubuntu-desktop-installer")
    if new_tags:
        report.setdefault("Tags", "")
        if report["Tags"]:
            report["Tags"] += " "
        report["Tags"] += " ".join(new_tags)


def add_info(report, ui):
    """This is an entry point to run cloud-init's apport functionality.

    Distros which want apport support will have a cloud-init package-hook at
    /usr/share/apport/package-hooks/cloud-init.py which defines an add_info
    function and returns the result of cloudinit.apport.add_info(report, ui).
    """
    if not has_apport:
        raise RuntimeError(
            "No apport imports discovered. Apport functionality disabled"
        )
    attach_cloud_init_logs(report, ui)
    attach_hwinfo(report, ui)
    attach_cloud_info(report, ui)
    attach_user_data(report, ui)
    attach_installer_files(report, ui)
    add_bug_tags(report)
    return True


# vi: ts=4 expandtab
