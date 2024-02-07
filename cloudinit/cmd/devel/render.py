#!/usr/bin/env python3

# This file is part of cloud-init. See LICENSE file for license information.

"""Debug jinja template rendering of user-data."""

import argparse
import logging
import os
import sys

from cloudinit.cmd.devel import read_cfg_paths
from cloudinit.handlers.jinja_template import (
    JinjaLoadError,
    JinjaSyntaxParsingException,
    NotJinjaError,
    render_jinja_payload_from_file,
)

NAME = "render"

LOG = logging.getLogger(__name__)


def get_parser(parser=None):
    """Build or extend and arg parser for jinja render utility.

    @param parser: Optional existing ArgumentParser instance representing the
        subcommand which will be extended to support the args of this utility.

    @returns: ArgumentParser with proper argument configuration.
    """
    if not parser:
        parser = argparse.ArgumentParser(prog=NAME, description=__doc__)
    parser.add_argument(
        "user_data", type=str, help="Path to the user-data file to render"
    )
    parser.add_argument(
        "-i",
        "--instance-data",
        type=str,
        help=(
            "Optional path to instance-data.json file. Defaults to"
            " /run/cloud-init/instance-data.json"
        ),
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        default=False,
        help="Add verbose messages during template render",
    )
    return parser


def render_template(user_data_path, instance_data_path=None, debug=False):
    """Render the provided user-data template file using instance-data values.

    Also setup CLI log handlers to report to stderr since this is a development
    utility which should be run by a human on the CLI.

    @return 0 on success, 1 on failure.
    """
    if instance_data_path:
        instance_data_fn = instance_data_path
    else:
        paths = read_cfg_paths()
        uid = os.getuid()
        redacted_data_fn = paths.get_runpath("instance_data")
        if uid == 0:
            instance_data_fn = paths.get_runpath("instance_data_sensitive")
            if not os.path.exists(instance_data_fn):
                LOG.warning(
                    "Missing root-readable %s. Using redacted %s instead.",
                    instance_data_fn,
                    redacted_data_fn,
                )
                instance_data_fn = redacted_data_fn
        else:
            instance_data_fn = redacted_data_fn
    if not os.path.exists(instance_data_fn):
        LOG.error("Missing instance-data.json file: %s", instance_data_fn)
        return 1
    try:
        with open(user_data_path) as stream:
            user_data = stream.read()
    except IOError:
        LOG.error("Missing user-data file: %s", user_data_path)
        return 1
    try:
        rendered_payload = render_jinja_payload_from_file(
            payload=user_data,
            payload_fn=user_data_path,
            instance_data_file=instance_data_fn,
            debug=True if debug else False,
        )
    except (JinjaLoadError, NotJinjaError) as e:
        LOG.error(
            "Cannot render from instance data due to exception: %s", repr(e)
        )
        return 1
    except JinjaSyntaxParsingException as e:
        LOG.error(
            "Failed to render templated user-data file '%s'. %s",
            user_data_path,
            str(e),
        )
        return 1
    if not rendered_payload:
        LOG.error("Unable to render user-data file: %s", user_data_path)
        return 1
    sys.stdout.write(rendered_payload)
    return 0


def handle_args(_name, args):
    return render_template(args.user_data, args.instance_data, args.debug)


if __name__ == "__main__":
    sys.exit(handle_args(NAME, get_parser().parse_args()))
