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

import boto.utils as boto_utils

# Versions of boto >= 2.6.0 (and possibly 2.5.2)
# try to lazily load the metadata backing, which
# doesn't work so well in cloud-init especially
# since the metadata is serialized and actions are
# performed where the metadata server may be blocked
# (thus the datasource will start failing) resulting
# in url exceptions when fields that do exist (or
# would have existed) do not exist due to the blocking
# that occurred.

# TODO(harlowja): https://github.com/boto/boto/issues/1401
# When boto finally moves to using requests, we should be able
# to provide it ssl details, it does not yet, so we can't provide them...


def _unlazy_dict(mp):
    if not isinstance(mp, (dict)):
        return mp
    # Walk over the keys/values which
    # forces boto to unlazy itself and
    # has no effect on dictionaries that
    # already have there items.
    for (_k, v) in mp.items():
        _unlazy_dict(v)
    return mp


def get_instance_userdata(api_version, metadata_address):
    # Note: boto.utils.get_instance_metadata returns '' for empty string
    # so the change from non-true to '' is not specifically necessary, but
    # this way cloud-init will get consistent behavior even if boto changed
    # in the future to return a None on "no user-data provided".
    ud = boto_utils.get_instance_userdata(api_version, None, metadata_address)
    if not ud:
        ud = ''
    return ud


def get_instance_metadata(api_version, metadata_address):
    metadata = boto_utils.get_instance_metadata(api_version, metadata_address)
    if not isinstance(metadata, (dict)):
        metadata = {}
    return _unlazy_dict(metadata)
