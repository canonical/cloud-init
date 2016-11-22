# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import six

DEF_MERGE_TYPE = 'replace'
MERGE_TYPES = ('append', 'prepend', DEF_MERGE_TYPE, 'no_replace')


def _has_any(what, *keys):
    for k in keys:
        if k in what:
            return True
    return False


class Merger(object):
    def __init__(self, merger, opts):
        self._merger = merger
        # Affects merging behavior...
        self._method = DEF_MERGE_TYPE
        for m in MERGE_TYPES:
            if m in opts:
                self._method = m
                break
        # Affect how recursive merging is done on other primitives
        self._recurse_str = _has_any(opts, 'recurse_str')
        self._recurse_dict = _has_any(opts, 'recurse_dict')
        self._recurse_array = _has_any(opts, 'recurse_array', 'recurse_list')

    def __str__(self):
        return ('ListMerger: (method=%s,recurse_str=%s,'
                'recurse_dict=%s,recurse_array=%s)') % (self._method,
                                                        self._recurse_str,
                                                        self._recurse_dict,
                                                        self._recurse_array)

    def _on_tuple(self, value, merge_with):
        return tuple(self._on_list(list(value), merge_with))

    def _on_list(self, value, merge_with):
        if (self._method == 'replace' and
                not isinstance(merge_with, (tuple, list))):
            return merge_with

        # Ok we now know that what we are merging with is a list or tuple.
        merged_list = []
        if self._method == 'prepend':
            merged_list.extend(merge_with)
            merged_list.extend(value)
            return merged_list
        elif self._method == 'append':
            merged_list.extend(value)
            merged_list.extend(merge_with)
            return merged_list

        def merge_same_index(old_v, new_v):
            if self._method == 'no_replace':
                # Leave it be...
                return old_v
            if isinstance(new_v, (list, tuple)) and self._recurse_array:
                return self._merger.merge(old_v, new_v)
            if isinstance(new_v, six.string_types) and self._recurse_str:
                return self._merger.merge(old_v, new_v)
            if isinstance(new_v, (dict)) and self._recurse_dict:
                return self._merger.merge(old_v, new_v)
            return new_v

        # Ok now we are replacing same indexes
        merged_list.extend(value)
        common_len = min(len(merged_list), len(merge_with))
        for i in range(0, common_len):
            merged_list[i] = merge_same_index(merged_list[i], merge_with[i])
        return merged_list

# vi: ts=4 expandtab
