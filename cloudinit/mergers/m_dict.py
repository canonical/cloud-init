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


class Merger(object):
    def __init__(self, merger, opts):
        self._merger = merger
        # Affects merging behavior...
        self._method = 'replace'
        for m in ['replace', 'no_replace']:
            if m in opts:
                self._method = m
                break
        # Affect how recursive merging is done on other primitives
        self._recurse_str = 'recurse_str' in opts
        self._recurse_dict = True
        self._recurse_array = 'recurse_array' in opts
        self._allow_delete = 'allow_delete' in opts

    def __str__(self):
        s = ('DictMerger: (method=%s,recurse_str=%s,'
             'recurse_dict=%s,recurse_array=%s,allow_delete=%s)')
        s  = s % (self._method,
                  self._recurse_str,
                  self._recurse_dict,
                  self._recurse_array,
                  self._allow_delete)
        return s

    def _do_dict_replace(self, value, merge_with, do_replace=True):

        def merge_same_key(old_v, new_v):
            if do_replace:
                return new_v
            if isinstance(new_v, (list, tuple)) and self._recurse_array:
                return self._merger.merge(old_v, new_v)
            if isinstance(new_v, (str, basestring)) and self._recurse_str:
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
            merged = self._do_dict_replace(dict(value), merge_with)
        elif self._method == 'no_replace':
            merged = self._do_dict_replace(dict(value), merge_with, False)
        else:
            raise NotImplementedError("Unknown merge type %s" % (self._method))
        return merged
