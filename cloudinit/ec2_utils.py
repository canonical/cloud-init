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

import pkg_resources
from pkg_resources import parse_version

import cloudinit.util as util
import cloudinit.url_helper as uh

import boto.utils as boto_utils

# Versions of boto >= 2.6.0 try to lazily load
# the metadata backing, which doesn't work so well
# in cloud-init especially since the metadata is
# serialized and actions are performed where the
# metadata server may be blocked (thus the datasource
# will start failing) resulting in url exceptions
# when fields that do exist (or would have existed)
# do not exist due to the blocking that occurred.

BOTO_LAZY = False
try:
    _boto_lib = pkg_resources.get_distribution('boto')
    if _boto_lib.parsed_version > parse_version("2.5.2"):
        BOTO_LAZY = True
except pkg_resources.DistributionNotFound:
    pass


def _unlazy_dict(mp):
    if not isinstance(mp, (dict)):
        return mp
    if not BOTO_LAZY:
        return mp
    for (k, v) in mp.items():
        _unlazy_dict(v)


def get_instance_userdata(api_version, metadata_address):
    ud = boto_utils.get_instance_userdata(api_version, None, metadata_address)
    if not ud:
        ud = ''
    return ud


def get_instance_metadata(api_version, metadata_address):
    metadata = boto_utils.get_instance_metadata(api_version, metadata_address)
    if not isinstance(metadata, (dict)):
        metadata = {}
    return _unlazy_dict(metadata)
