# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

from urlparse import (urlparse, urlunparse)

import functools
import json
import urllib

from cloudinit import log as logging
from cloudinit import util

LOG = logging.getLogger(__name__)


def combine_url(base, add_on):
    base_parsed = list(urlparse(base))
    path = base_parsed[2]
    if path and not path.endswith("/"):
        path += "/"
    path += urllib.quote(str(add_on), safe="/:")
    base_parsed[2] = path
    return urlunparse(base_parsed)


# See: http://bit.ly/TyoUQs
#
# Since boto metadata reader uses the old urllib which does not
# support ssl, we need to ahead and create our own reader which
# works the same as the boto one (for now).
class MetadataMaterializer(object):
    def __init__(self, blob, base_url, caller):
        self._blob = blob
        self._md = None
        self._base_url = base_url
        self._caller = caller

    def _parse(self, blob):
        leaves = {}
        children = []
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
                    checked_ident = util.safe_int(ident)
                    if checked_ident is not None:
                        resource = "%s/openssh-key" % (checked_ident)
                        field_name = sub_contents
                leaves[field_name] = resource
        return (leaves, children)

    def materialize(self):
        if self._md is not None:
            return self._md
        self._md = self._materialize(self._blob, self._base_url)
        return self._md

    def _decode_leaf_blob(self, blob):
        if not blob:
            return blob
        stripped_blob = blob.strip()
        if stripped_blob.startswith("{") and stripped_blob.endswith("}"):
            # Assume and try with json
            try:
                return json.loads(blob)
            except (ValueError, TypeError):
                pass
        if blob.find("\n") != -1:
            return blob.splitlines()
        return blob

    def _materialize(self, blob, base_url):
        (leaves, children) = self._parse(blob)
        child_contents = {}
        for c in children:
            child_url = combine_url(base_url, c)
            if not child_url.endswith("/"):
                child_url += "/"
            child_blob = str(self._caller(child_url))
            child_contents[c] = self._materialize(child_blob, child_url)
        leaf_contents = {}
        for (field, resource) in leaves.items():
            leaf_url = combine_url(base_url, resource)
            leaf_blob = str(self._caller(leaf_url))
            leaf_contents[field] = self._decode_leaf_blob(leaf_blob)
        joined = {}
        joined.update(child_contents)
        for field in leaf_contents.keys():
            if field in joined:
                LOG.warn("Duplicate key found in results from %s", base_url)
            else:
                joined[field] = leaf_contents[field]
        return joined


def get_instance_userdata(api_version='latest',
                          metadata_address='http://169.254.169.254',
                          ssl_details=None, timeout=5, retries=5):
    ud_url = combine_url(metadata_address, api_version)
    ud_url = combine_url(ud_url, 'user-data')
    try:
        response = util.read_file_or_url(ud_url,
                                         ssl_details=ssl_details,
                                         timeout=timeout,
                                         retries=retries)
        return str(response)
    except Exception:
        util.logexc(LOG, "Failed fetching userdata from url %s", ud_url)
        return None


def get_instance_metadata(api_version='latest',
                          metadata_address='http://169.254.169.254',
                          ssl_details=None, timeout=5, retries=5):
    md_url = combine_url(metadata_address, api_version)
    md_url = combine_url(md_url, 'meta-data')
    caller = functools.partial(util.read_file_or_url,
                               ssl_details=ssl_details, timeout=timeout,
                               retries=retries)

    try:
        response = caller(md_url)
        materializer = MetadataMaterializer(str(response), md_url, caller)
        md = materializer.materialize()
        if not isinstance(md, (dict)):
            md = {}
        return md
    except Exception:
        util.logexc(LOG, "Failed fetching metadata from url %s", md_url)
        return {}
