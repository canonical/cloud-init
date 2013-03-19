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
        self._discard_non = 'discard_non_list' in opts
        self._extend = 'extend' in opts

    def _on_tuple(self, value, merge_with):
        return self._on_list(list(value), merge_with)

    # On encountering a list or tuple type this action will be applied
    # a new list will be returned, if the value to merge with is itself
    # a list and we have been told to 'extend', then the value here will
    # be extended with the other list. If in 'extend' mode then we will
    # attempt to merge instead, which means that values from the list
    # to merge with will replace values in te original list (they will
    # also be merged recursively).
    #
    # If the value to merge with is not a list, and we are set to discared
    # then no modifications will take place, otherwise we will just append
    # the value to merge with onto the end of our own list.
    def _on_list(self, value, merge_with):
        new_value = list(value)
        if isinstance(merge_with, (tuple, list)):
            if self._extend:
                new_value.extend(merge_with)
            else:
                return new_value
        else:
            if not self._discard_non:
                new_value.append(merge_with)
        return new_value
