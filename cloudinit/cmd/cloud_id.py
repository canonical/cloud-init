#!/usr/bin/env python3

# This file is part of cloud-init. See LICENSE file for license information.

"""Commandline utility to list the canonical cloud-id for an instance."""

import argparse
import json
import sys

from cloudinit.cmd.devel import read_cfg_paths
from cloudinit.cmd.status import UXAppStatus, get_status_details
from cloudinit.sources import METADATA_UNKNOWN, canonical_cloud_id
from cloudinit.util import error

NAME = "cloud-id"


def get_parser(parser=None):
    """Build or extend an arg parser for the cloud-id utility.

    @param parser: Optional existing ArgumentParser instance representing the
        query subcommand which will be extended to support the args of
        this utility.

    @returns: ArgumentParser with proper argument configuration.
    """
    default_instance_json = read_cfg_paths().get_runpath("instance_data")
    if not parser:
        parser = argparse.ArgumentParser(
            prog=NAME,
            description="Report the canonical cloud-id for this instance",
        )
    parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        default=False,
        help="Report all standardized cloud-id information as json.",
    )
    parser.add_argument(
        "-l",
        "--long",
        action="store_true",
        default=False,
        help="Report extended cloud-id information as tab-delimited string.",
    )
    parser.add_argument(
        "-i",
        "--instance-data",
        type=str,
        default=default_instance_json,
        help=(
            "Path to instance-data.json file. "
            f"Default is {default_instance_json}"
        ),
    )
    return parser


def handle_args(name, args):
    """Handle calls to 'cloud-id' cli.

    Print the canonical cloud-id on which the instance is running.

    @return: 0 on success, 1 on error, 2 on disabled, 3 on cloud-init not run.
    """
    status_details = get_status_details()
    if status_details.status == UXAppStatus.DISABLED:
        sys.stdout.write("{0}\n".format(status_details.status.value))
        return 2
    elif status_details.status == UXAppStatus.NOT_RUN:
        sys.stdout.write("{0}\n".format(status_details.status.value))
        return 3

    try:
        with open(args.instance_data) as file:
            instance_data = json.load(file)
    except IOError:
        return error(
            "File not found '%s'. Provide a path to instance data json file"
            " using --instance-data" % args.instance_data
        )
    except ValueError as e:
        return error(
            "File '%s' is not valid json. %s" % (args.instance_data, e)
        )
    v1 = instance_data.get("v1", {})
    cloud_id = canonical_cloud_id(
        v1.get("cloud_name", METADATA_UNKNOWN),
        v1.get("region", METADATA_UNKNOWN),
        v1.get("platform", METADATA_UNKNOWN),
    )
    if args.json:
        sys.stderr.write("DEPRECATED: Use: cloud-init query v1\n")
        v1["cloud_id"] = cloud_id
        response = json.dumps(  # Pretty, sorted json
            v1, indent=1, sort_keys=True, separators=(",", ": ")
        )
    elif args.long:
        response = "%s\t%s" % (cloud_id, v1.get("region", METADATA_UNKNOWN))
    else:
        response = cloud_id
    sys.stdout.write("%s\n" % response)
    return 0


def main():
    """Tool to query specific instance-data values."""
    parser = get_parser()
    sys.exit(handle_args(NAME, parser.parse_args()))


if __name__ == "__main__":
    main()
