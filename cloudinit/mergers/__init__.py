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

import re

from cloudinit import importer
from cloudinit import log as logging
from cloudinit import util

NAME_MTCH = re.compile(r"(^[a-zA-Z_][A-Za-z0-9_]*)\((.*?)\)$")

LOG = logging.getLogger(__name__)


class UnknownMerger(object):
    # Named differently so auto-method finding
    # doesn't pick this up if there is ever a type
    # named "unknown"
    def _handle_unknown(self, meth_wanted, value, merge_with):
        return value

    def merge(self, source, merge_with):
        type_name = util.obj_name(source)
        type_name = type_name.lower()
        method_name = "_on_%s" % (type_name)
        meth = None
        args = [source, merge_with]
        if hasattr(self, method_name):
            meth = getattr(self, method_name)
        if not meth:
            meth = self._handle_unknown
            args.insert(0, method_name)
        return meth(*args)


class LookupMerger(UnknownMerger):
    def __init__(self, lookups=None):
        UnknownMerger.__init__(self)
        if lookups is None:
            self._lookups = []
        else:
            self._lookups = lookups

    def _handle_unknown(self, meth_wanted, value, merge_with):
        meth = None
        for merger in self._lookups:
            if hasattr(merger, meth_wanted):
                # First one that has that method/attr gets to be
                # the one that will be called
                meth = getattr(merger, meth_wanted)
                break
        if not meth:
            return UnknownMerger._handle_unknown(self, meth_wanted,
                                                 value, merge_with)
        return meth(value, merge_with)


def _extract_merger_names(merge_how):
    names = []
    for m_name in merge_how.split("+"):
        # Canonicalize the name (so that it can be found
        # even when users alter it in various ways)
        m_name = m_name.lower().strip()
        m_name = m_name.replace("-", "_")
        if not m_name:
            continue
        names.append(m_name)
    return names


def construct(merge_how):
    mergers_to_be = []
    for name in _extract_merger_names(merge_how):
        match = NAME_MTCH.match(name)
        if not match:
            msg = "Matcher identifer '%s' is not in the right format" % (name)
            raise ValueError(msg)
        (m_name, m_ops) = match.groups()
        m_ops = m_ops.strip().split(",")
        m_ops = [m.strip().lower() for m in m_ops if m.strip()]
        merger_locs = importer.find_module(m_name,
                                           [__name__],
                                           ['Merger'])
        if not merger_locs:
            msg = "Could not find merger named '%s'" % (m_name)
            raise ImportError(msg)
        else:
            mod = importer.import_module(merger_locs[0])
            mod_attr = getattr(mod, 'Merger')
            mergers_to_be.append((mod_attr, m_ops))
    # Now form them...
    mergers = []
    root = LookupMerger(mergers)
    for (attr, opts) in mergers_to_be:
        mergers.append(attr(root, opts))
    return root