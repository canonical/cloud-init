#!/usr/bin/env python3

# This file is part of cloud-init. See LICENSE file for license information.

"""Query standardized instance metadata provided to machine, returning a JSON
structure.

Some instance-data values may be binary on some platforms, such as userdata and
vendordata. Attempt to decompress and decode UTF-8 any binary values.

Any binary values in the instance metadata will be base64-encoded and prefixed
with "ci-b64:" in the output. userdata and, where applicable, vendordata may
be provided to the machine gzip-compressed (and therefore as binary data).
query will attempt to decompress these to a string before emitting the JSON
output; if this fails, they are treated as binary.
"""

import argparse
import logging
import os
import sys
from errno import EACCES

from cloudinit import atomic_helper, util
from cloudinit.cmd.devel import read_cfg_paths
from cloudinit.handlers.jinja_template import (
    convert_jinja_instance_data,
    get_jinja_variable_alias,
    render_jinja_payload,
)
from cloudinit.sources import REDACT_SENSITIVE_VALUE
from cloudinit.templater import JinjaSyntaxParsingException

NAME = "query"
LOG = logging.getLogger(__name__)


def get_parser(parser=None):
    """Build or extend an arg parser for query utility.

    @param parser: Optional existing ArgumentParser instance representing the
        query subcommand which will be extended to support the args of
        this utility.

    @returns: ArgumentParser with proper argument configuration.
    """
    if not parser:
        parser = argparse.ArgumentParser(prog=NAME, description=__doc__)
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        default=False,
        help="Add verbose messages during template render",
    )
    parser.add_argument(
        "-i",
        "--instance-data",
        type=str,
        help=(
            "Path to instance-data.json file. Default is "
            f"{read_cfg_paths().get_runpath('instance_data')}"
        ),
    )
    parser.add_argument(
        "-l",
        "--list-keys",
        action="store_true",
        default=False,
        help=(
            "List query keys available at the provided instance-data"
            " <varname>."
        ),
    )
    parser.add_argument(
        "-u",
        "--user-data",
        type=str,
        help=(
            "Path to user-data file. Default is"
            " /var/lib/cloud/instance/user-data.txt"
        ),
    )
    parser.add_argument(
        "-v",
        "--vendor-data",
        type=str,
        help=(
            "Path to vendor-data file. Default is"
            " /var/lib/cloud/instance/vendor-data.txt"
        ),
    )
    parser.add_argument(
        "varname",
        type=str,
        nargs="?",
        help=(
            "A dot-delimited specific variable to query from"
            " instance-data. For example: v1.local_hostname. If the"
            " value is not JSON serializable, it will be base64-encoded and"
            ' will contain the prefix "ci-b64:". '
        ),
    )
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        default=False,
        dest="dump_all",
        help="Dump all available instance-data",
    )
    parser.add_argument(
        "-f",
        "--format",
        type=str,
        dest="format",
        help=(
            "Optionally specify a custom output format string. Any"
            " instance-data variable can be specified between double-curly"
            ' braces. For example -f "{{ v2.cloud_name }}"'
        ),
    )
    return parser


def load_userdata(ud_file_path):
    """Attempt to return a string of user-data from ud_file_path

    Attempt to decode or decompress if needed.
    If unable to decode the content, raw bytes will be returned.

    @returns: String of uncompressed userdata if possible, otherwise bytes.
    """
    bdata = util.load_binary_file(ud_file_path, quiet=True)
    try:
        return bdata.decode("utf-8")
    except UnicodeDecodeError:
        return util.decomp_gzip(bdata, quiet=False, decode=True)


def _read_instance_data(instance_data, user_data, vendor_data) -> dict:
    """Return a dict of merged instance-data, vendordata and userdata.

    The dict will contain supplemental userdata and vendordata keys sourced
    from default user-data and vendor-data files.

    Non-root users will have redacted INSTANCE_JSON_FILE content and redacted
    vendordata and userdata values.

    :raise: IOError/OSError on absence of instance-data.json file or invalid
        access perms.
    """
    uid = os.getuid()
    paths = read_cfg_paths()
    if instance_data:
        instance_data_fn = instance_data
    else:
        redacted_data_fn = paths.get_runpath("instance_data")
        if uid == 0:
            sensitive_data_fn = paths.get_runpath("instance_data_sensitive")
            if os.path.exists(sensitive_data_fn):
                instance_data_fn = sensitive_data_fn
            else:
                LOG.warning(
                    "Missing root-readable %s. Using redacted %s instead.",
                    sensitive_data_fn,
                    redacted_data_fn,
                )
                instance_data_fn = redacted_data_fn
        else:
            instance_data_fn = redacted_data_fn
    if user_data:
        user_data_fn = user_data
    else:
        user_data_fn = os.path.join(paths.instance_link, "user-data.txt")
    if vendor_data:
        vendor_data_fn = vendor_data
    else:
        vendor_data_fn = os.path.join(paths.instance_link, "vendor-data.txt")
    combined_cloud_config_fn = paths.get_runpath("combined_cloud_config")

    try:
        instance_json = util.load_text_file(instance_data_fn)
    except (IOError, OSError) as e:
        if e.errno == EACCES:
            LOG.error("No read permission on '%s'. Try sudo", instance_data_fn)
        else:
            LOG.error("Missing instance-data file: %s", instance_data_fn)
        raise

    instance_data = util.load_json(instance_json)
    try:
        combined_cloud_config = util.load_json(
            util.load_text_file(combined_cloud_config_fn)
        )
    except (IOError, OSError):
        # File will not yet be present in init-local stage.
        # It's created in `init` when vendor-data and user-data are processed.
        combined_cloud_config = None

    if uid != 0:
        instance_data["userdata"] = "<%s> file:%s" % (
            REDACT_SENSITIVE_VALUE,
            user_data_fn,
        )
        instance_data["vendordata"] = "<%s> file:%s" % (
            REDACT_SENSITIVE_VALUE,
            vendor_data_fn,
        )
        instance_data["combined_cloud_config"] = "<%s> file:%s" % (
            REDACT_SENSITIVE_VALUE,
            combined_cloud_config_fn,
        )
    else:
        instance_data["userdata"] = load_userdata(user_data_fn)
        instance_data["vendordata"] = load_userdata(vendor_data_fn)
        instance_data["combined_cloud_config"] = combined_cloud_config
    return instance_data


def _find_instance_data_leaf_by_varname_path(
    jinja_vars_without_aliases: dict,
    jinja_vars_with_aliases: dict,
    varname: str,
    list_keys: bool,
):
    """Return the value of the dot-delimited varname path in instance-data

    Split a dot-delimited jinja variable name path into components, walk the
    path components into the instance_data and look up a matching jinja
    variable name or cloud-init's underscore-delimited key aliases.

    :raises: ValueError when varname represents an invalid key name or path or
        if list-keys is provided by varname isn't a dict object.
    """
    walked_key_path = ""
    response = jinja_vars_without_aliases
    for key_path_part in varname.split("."):
        try:
            # Walk key path using complete aliases dict, yet response
            # should only contain jinja_without_aliases
            jinja_vars_with_aliases = jinja_vars_with_aliases[key_path_part]
        except KeyError as e:
            if walked_key_path:
                msg = "instance-data '{key_path}' has no '{leaf}'".format(
                    leaf=key_path_part, key_path=walked_key_path
                )
            else:
                msg = "Undefined instance-data key '{}'".format(varname)
            raise ValueError(msg) from e
        if key_path_part in response:
            response = response[key_path_part]
        else:  # We are an underscore_delimited key alias
            for key in response:
                if get_jinja_variable_alias(key) == key_path_part:
                    response = response[key]
                    break
        if walked_key_path:
            walked_key_path += "."
        walked_key_path += key_path_part
    return response


def handle_args(name, args):
    """Handle calls to 'cloud-init query' as a subcommand."""
    if not any([args.list_keys, args.varname, args.format, args.dump_all]):
        LOG.error(
            "Expected one of the options: --all, --format,"
            " --list-keys or varname"
        )
        get_parser().print_help()
        return 1
    try:
        instance_data = _read_instance_data(
            args.instance_data, args.user_data, args.vendor_data
        )
    except (IOError, OSError):
        return 1
    if args.format:
        payload = "## template: jinja\n{fmt}".format(fmt=args.format)
        try:
            rendered_payload = render_jinja_payload(
                payload=payload,
                payload_fn="query command line",
                instance_data=instance_data,
                debug=True if args.debug else False,
            )
        except JinjaSyntaxParsingException as e:
            LOG.error(
                "Failed to render templated data. %s",
                str(e),
            )
            return 1
        if rendered_payload:
            print(rendered_payload)
            return 0
        return 1

    # If not rendering a structured format above, query output will be either:
    #  - JSON dump of all instance-data/jinja variables
    #  - JSON dump of a value at an dict path into the instance-data dict.
    #  - a list of keys for a specific dict path into the instance-data dict.
    response = convert_jinja_instance_data(instance_data)
    if args.varname:
        jinja_vars_with_aliases = convert_jinja_instance_data(
            instance_data, include_key_aliases=True
        )
        try:
            response = _find_instance_data_leaf_by_varname_path(
                jinja_vars_without_aliases=response,
                jinja_vars_with_aliases=jinja_vars_with_aliases,
                varname=args.varname,
                list_keys=args.list_keys,
            )
        except (KeyError, ValueError) as e:
            LOG.error(e)
            return 1
    if args.list_keys:
        if not isinstance(response, dict):
            LOG.error(
                "--list-keys provided but '%s' is not a dict", args.varname
            )
            return 1
        response = "\n".join(sorted(response.keys()))
    if not isinstance(response, str):
        response = atomic_helper.json_dumps(response)
    print(response)
    return 0


def main():
    """Tool to query specific instance-data values."""
    parser = get_parser()
    sys.exit(handle_args(NAME, parser.parse_args()))


if __name__ == "__main__":
    main()
