# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import functools
import json

from cloudinit import log as logging
from cloudinit import url_helper
from cloudinit import util

LOG = logging.getLogger(__name__)
SKIP_USERDATA_CODES = frozenset([url_helper.NOT_FOUND])


class MetadataLeafDecoder(object):
    """Decodes a leaf blob into something meaningful."""

    def _maybe_json_object(self, text):
        if not text:
            return False
        text = text.strip()
        if text.startswith("{") and text.endswith("}"):
            return True
        return False

    def __call__(self, field, blob):
        if not blob:
            return blob
        try:
            blob = util.decode_binary(blob)
        except UnicodeDecodeError:
            return blob
        if self._maybe_json_object(blob):
            try:
                # Assume it's json, unless it fails parsing...
                return json.loads(blob)
            except (ValueError, TypeError) as e:
                LOG.warn("Field %s looked like a json object, but it was"
                         " not: %s", field, e)
        if blob.find("\n") != -1:
            return blob.splitlines()
        return blob


# See: http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/
#         ec2-instance-metadata.html
class MetadataMaterializer(object):
    def __init__(self, blob, base_url, caller, leaf_decoder=None):
        self._blob = blob
        self._md = None
        self._base_url = base_url
        self._caller = caller
        if leaf_decoder is None:
            self._leaf_decoder = MetadataLeafDecoder()
        else:
            self._leaf_decoder = leaf_decoder

    def _parse(self, blob):
        leaves = {}
        children = []
        blob = util.decode_binary(blob)

        if not blob:
            return (leaves, children)

        def has_children(item):
            if item.endswith("/"):
                return True
            else:
                return False

        def get_name(item):
            if item.endswith("/"):
                return item.rstrip("/")
            return item

        for field in blob.splitlines():
            field = field.strip()
            field_name = get_name(field)
            if not field or not field_name:
                continue
            if has_children(field):
                if field_name not in children:
                    children.append(field_name)
            else:
                contents = field.split("=", 1)
                resource = field_name
                if len(contents) > 1:
                    # What a PITA...
                    (ident, sub_contents) = contents
                    ident = util.safe_int(ident)
                    if ident is not None:
                        resource = "%s/openssh-key" % (ident)
                        field_name = sub_contents
                leaves[field_name] = resource
        return (leaves, children)

    def materialize(self):
        if self._md is not None:
            return self._md
        self._md = self._materialize(self._blob, self._base_url)
        return self._md

    def _materialize(self, blob, base_url):
        (leaves, children) = self._parse(blob)
        child_contents = {}
        for c in children:
            child_url = url_helper.combine_url(base_url, c)
            if not child_url.endswith("/"):
                child_url += "/"
            child_blob = self._caller(child_url)
            child_contents[c] = self._materialize(child_blob, child_url)
        leaf_contents = {}
        for (field, resource) in leaves.items():
            leaf_url = url_helper.combine_url(base_url, resource)
            leaf_blob = self._caller(leaf_url)
            leaf_contents[field] = self._leaf_decoder(field, leaf_blob)
        joined = {}
        joined.update(child_contents)
        for field in leaf_contents.keys():
            if field in joined:
                LOG.warn("Duplicate key found in results from %s", base_url)
            else:
                joined[field] = leaf_contents[field]
        return joined


def _skip_retry_on_codes(status_codes, _request_args, cause):
    """Returns if a request should retry based on a given set of codes that
    case retrying to be stopped/skipped.
    """
    return cause.code in status_codes


def get_instance_userdata(api_version='latest',
                          metadata_address='http://169.254.169.254',
                          ssl_details=None, timeout=5, retries=5):
    ud_url = url_helper.combine_url(metadata_address, api_version)
    ud_url = url_helper.combine_url(ud_url, 'user-data')
    user_data = ''
    try:
        # It is ok for userdata to not exist (thats why we are stopping if
        # NOT_FOUND occurs) and just in that case returning an empty string.
        exception_cb = functools.partial(_skip_retry_on_codes,
                                         SKIP_USERDATA_CODES)
        response = util.read_file_or_url(ud_url,
                                         ssl_details=ssl_details,
                                         timeout=timeout,
                                         retries=retries,
                                         exception_cb=exception_cb)
        user_data = response.contents
    except url_helper.UrlError as e:
        if e.code not in SKIP_USERDATA_CODES:
            util.logexc(LOG, "Failed fetching userdata from url %s", ud_url)
    except Exception:
        util.logexc(LOG, "Failed fetching userdata from url %s", ud_url)
    return user_data


def get_instance_metadata(api_version='latest',
                          metadata_address='http://169.254.169.254',
                          ssl_details=None, timeout=5, retries=5,
                          leaf_decoder=None):
    md_url = url_helper.combine_url(metadata_address, api_version)
    # Note, 'meta-data' explicitly has trailing /.
    # this is required for CloudStack (LP: #1356855)
    md_url = url_helper.combine_url(md_url, 'meta-data/')
    caller = functools.partial(util.read_file_or_url,
                               ssl_details=ssl_details, timeout=timeout,
                               retries=retries)

    def mcaller(url):
        return caller(url).contents

    try:
        response = caller(md_url)
        materializer = MetadataMaterializer(response.contents,
                                            md_url, mcaller,
                                            leaf_decoder=leaf_decoder)
        md = materializer.materialize()
        if not isinstance(md, (dict)):
            md = {}
        return md
    except Exception:
        util.logexc(LOG, "Failed fetching metadata from url %s", md_url)
        return {}

# vi: ts=4 expandtab
