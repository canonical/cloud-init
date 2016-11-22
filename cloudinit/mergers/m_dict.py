# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import six

DEF_MERGE_TYPE = 'no_replace'
MERGE_TYPES = ('replace', DEF_MERGE_TYPE,)


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
        # Affect how recursive merging is done on other primitives.
        self._recurse_str = 'recurse_str' in opts
        self._recurse_array = _has_any(opts, 'recurse_array', 'recurse_list')
        self._allow_delete = 'allow_delete' in opts
        # Backwards compat require this to be on.
        self._recurse_dict = True

    def __str__(self):
        s = ('DictMerger: (method=%s,recurse_str=%s,'
             'recurse_dict=%s,recurse_array=%s,allow_delete=%s)')
        s = s % (self._method, self._recurse_str,
                 self._recurse_dict, self._recurse_array, self._allow_delete)
        return s

    def _do_dict_replace(self, value, merge_with, do_replace):

        def merge_same_key(old_v, new_v):
            if do_replace:
                return new_v
            if isinstance(new_v, (list, tuple)) and self._recurse_array:
                return self._merger.merge(old_v, new_v)
            if isinstance(new_v, six.string_types) and self._recurse_str:
                return self._merger.merge(old_v, new_v)
            if isinstance(new_v, (dict)) and self._recurse_dict:
                return self._merger.merge(old_v, new_v)
            # Otherwise leave it be...
            return old_v

        for (k, v) in merge_with.items():
            if k in value:
                if v is None and self._allow_delete:
                    value.pop(k)
                else:
                    value[k] = merge_same_key(value[k], v)
            else:
                value[k] = v
        return value

    def _on_dict(self, value, merge_with):
        if not isinstance(merge_with, (dict)):
            return value
        if self._method == 'replace':
            merged = self._do_dict_replace(dict(value), merge_with, True)
        elif self._method == 'no_replace':
            merged = self._do_dict_replace(dict(value), merge_with, False)
        else:
            raise NotImplementedError("Unknown merge type %s" % (self._method))
        return merged

# vi: ts=4 expandtab
