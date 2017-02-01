# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import re

import six

from cloudinit import importer
from cloudinit import log as logging
from cloudinit import type_utils

NAME_MTCH = re.compile(r"(^[a-zA-Z_][A-Za-z0-9_]*)\((.*?)\)$")

LOG = logging.getLogger(__name__)
DEF_MERGE_TYPE = "list()+dict()+str()"
MERGER_PREFIX = 'm_'
MERGER_ATTR = 'Merger'


class UnknownMerger(object):
    # Named differently so auto-method finding
    # doesn't pick this up if there is ever a type
    # named "unknown"
    def _handle_unknown(self, _meth_wanted, value, _merge_with):
        return value

    # This merging will attempt to look for a '_on_X' method
    # in our own object for a given object Y with type X,
    # if found it will be called to perform the merge of a source
    # object and a object to merge_with.
    #
    # If not found the merge will be given to a '_handle_unknown'
    # function which can decide what to do wit the 2 values.
    def merge(self, source, merge_with):
        type_name = type_utils.obj_name(source)
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

    def __str__(self):
        return 'LookupMerger: (%s)' % (len(self._lookups))

    # For items which can not be merged by the parent this object
    # will lookup in a internally maintained set of objects and
    # find which one of those objects can perform the merge. If
    # any of the contained objects have the needed method, they
    # will be called to perform the merge.
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


def dict_extract_mergers(config):
    parsed_mergers = []
    raw_mergers = config.pop('merge_how', None)
    if raw_mergers is None:
        raw_mergers = config.pop('merge_type', None)
    if raw_mergers is None:
        return parsed_mergers
    if isinstance(raw_mergers, six.string_types):
        return string_extract_mergers(raw_mergers)
    for m in raw_mergers:
        if isinstance(m, (dict)):
            name = m['name']
            name = name.replace("-", "_").strip()
            opts = m['settings']
        else:
            name = m[0]
            if len(m) >= 2:
                opts = m[1:]
            else:
                opts = []
        if name:
            parsed_mergers.append((name, opts))
    return parsed_mergers


def string_extract_mergers(merge_how):
    parsed_mergers = []
    for m_name in merge_how.split("+"):
        # Canonicalize the name (so that it can be found
        # even when users alter it in various ways)
        m_name = m_name.lower().strip()
        m_name = m_name.replace("-", "_")
        if not m_name:
            continue
        match = NAME_MTCH.match(m_name)
        if not match:
            msg = ("Matcher identifer '%s' is not in the right format" %
                   (m_name))
            raise ValueError(msg)
        (m_name, m_ops) = match.groups()
        m_ops = m_ops.strip().split(",")
        m_ops = [m.strip().lower() for m in m_ops if m.strip()]
        parsed_mergers.append((m_name, m_ops))
    return parsed_mergers


def default_mergers():
    return tuple(string_extract_mergers(DEF_MERGE_TYPE))


def construct(parsed_mergers):
    mergers_to_be = []
    for (m_name, m_ops) in parsed_mergers:
        if not m_name.startswith(MERGER_PREFIX):
            m_name = MERGER_PREFIX + str(m_name)
        merger_locs, looked_locs = importer.find_module(m_name,
                                                        [__name__],
                                                        [MERGER_ATTR])
        if not merger_locs:
            msg = ("Could not find merger module named '%s' "
                   "with attribute '%s' (searched %s)") % (m_name,
                                                           MERGER_ATTR,
                                                           looked_locs)
            raise ImportError(msg)
        else:
            mod = importer.import_module(merger_locs[0])
            mod_attr = getattr(mod, MERGER_ATTR)
            mergers_to_be.append((mod_attr, m_ops))
    # Now form them...
    mergers = []
    root = LookupMerger(mergers)
    for (attr, opts) in mergers_to_be:
        mergers.append(attr(root, opts))
    return root

# vi: ts=4 expandtab
