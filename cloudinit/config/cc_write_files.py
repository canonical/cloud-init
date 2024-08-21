# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Write Files: write arbitrary files"""

import base64
import logging
import os
from typing import Optional

from cloudinit import url_helper, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE

DEFAULT_PERMS = 0o644
DEFAULT_DEFER = False
TEXT_PLAIN_ENC = "text/plain"

LOG = logging.getLogger(__name__)

meta: MetaSchema = {
    "id": "cc_write_files",
    "distros": ["all"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["write_files"],
}  # type: ignore


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    file_list = cfg.get("write_files", [])
    filtered_files = [
        f
        for f in file_list
        if not util.get_cfg_option_bool(f, "defer", DEFAULT_DEFER)
    ]
    if not filtered_files:
        LOG.debug(
            "Skipping module named %s,"
            " no/empty 'write_files' key in configuration",
            name,
        )
        return
    ssl_details = util.fetch_ssl_details(cloud.paths)
    write_files(name, filtered_files, cloud.distro.default_owner, ssl_details)


def canonicalize_extraction(encoding_type):
    if not encoding_type:
        encoding_type = ""
    encoding_type = encoding_type.lower().strip()
    if encoding_type in ["gz", "gzip"]:
        return ["application/x-gzip"]
    if encoding_type in ["gz+base64", "gzip+base64", "gz+b64", "gzip+b64"]:
        return ["application/base64", "application/x-gzip"]
    # Yaml already encodes binary data as base64 if it is given to the
    # yaml file as binary, so those will be automatically decoded for you.
    # But the above b64 is just for people that are more 'comfortable'
    # specifying it manually (which might be a possibility)
    if encoding_type in ["b64", "base64"]:
        return ["application/base64"]
    if encoding_type == TEXT_PLAIN_ENC:
        return [TEXT_PLAIN_ENC]
    if encoding_type:
        LOG.warning(
            "Unknown encoding type %s, assuming %s",
            encoding_type,
            TEXT_PLAIN_ENC,
        )
    return [TEXT_PLAIN_ENC]


def write_files(name, files, owner: str, ssl_details: Optional[dict] = None):
    if not files:
        return

    for i, f_info in enumerate(files):
        path = f_info.get("path")
        if not path:
            LOG.warning(
                "No path provided to write for entry %s in module %s",
                i + 1,
                name,
            )
            continue
        path = os.path.abspath(path)
        # Read content from provided URL, if any, or decode from inline
        contents = read_url_or_decode(
            f_info.get("source", None),
            ssl_details,
            f_info.get("content", None),
            f_info.get("encoding", None),
        )
        if contents is None:
            LOG.warning(
                "No content could be loaded for entry %s in module %s;"
                " skipping",
                i + 1,
                name,
            )
            continue
        # Only create the file if content exists. This will not happen, for
        # example, if the URL fails and no inline content was provided
        (u, g) = util.extract_usergroup(f_info.get("owner", owner))
        perms = decode_perms(f_info.get("permissions"), DEFAULT_PERMS)
        omode = "ab" if util.get_cfg_option_bool(f_info, "append") else "wb"
        util.write_file(
            path, contents, omode=omode, mode=perms, user=u, group=g
        )
        util.chownbyname(path, u, g)


def decode_perms(perm, default):
    if perm is None:
        return default
    try:
        if isinstance(perm, (int, float)):
            # Just 'downcast' it (if a float)
            return int(perm)
        else:
            # Force to string and try octal conversion
            return int(str(perm), 8)
    except (TypeError, ValueError):
        reps = []
        for r in (perm, default):
            try:
                reps.append("%o" % r)
            except TypeError:
                reps.append("%r" % r)
        LOG.warning("Undecodable permissions %s, returning default %s", *reps)
        return default


def read_url_or_decode(source, ssl_details, content, encoding):
    url = None if source is None else source.get("uri", None)
    use_url = bool(url)
    # Special case: empty URL and content. Write a blank file
    if content is None and not use_url:
        return ""
    # Fetch file content from source URL, if provided
    result = None
    if use_url:
        try:
            # NOTE: These retry parameters are arbitrarily chosen defaults.
            # They have no significance, and may be changed if appropriate
            result = url_helper.read_file_or_url(
                url,
                headers=source.get("headers", None),
                retries=3,
                sec_between=3,
                ssl_details=ssl_details,
            ).contents
        except Exception:
            util.logexc(
                LOG,
                'Failed to retrieve contents from source "%s"; falling back to'
                ' data from "contents" key',
                url,
            )
            use_url = False
    # If inline content is provided, and URL is not provided or is
    # inaccessible, parse the former
    if content is not None and not use_url:
        # NOTE: This is not simply an "else"! Notice that `use_url` can change
        # in the previous "if" block
        extractions = canonicalize_extraction(encoding)
        result = extract_contents(content, extractions)
    return result


def extract_contents(contents, extraction_types):
    result = contents
    for t in extraction_types:
        if t == "application/x-gzip":
            result = util.decomp_gzip(result, quiet=False, decode=False)
        elif t == "application/base64":
            result = base64.b64decode(result)
        elif t == TEXT_PLAIN_ENC:
            pass
    return result
