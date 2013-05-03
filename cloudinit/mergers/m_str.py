# -*- coding: utf-8 -*-
# vi: ts=4 expandtab
#
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3, as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.


class Merger(object):
    def __init__(self, _merger, opts):
        self._append = 'append' in opts

    def __str__(self):
        return 'StringMerger: (append=%s)' % (self._append)

    # On encountering a unicode object to merge value with
    # we will for now just proxy into the string method to let it handle it.
    def _on_unicode(self, value, merge_with):
        return self._on_str(value, merge_with)

    # On encountering a string object to merge with we will
    # perform the following action, if appending we will
    # merge them together, otherwise we will just return value.
    def _on_str(self, value, merge_with):
        if not isinstance(value, (basestring)):
            return merge_with
        if not self._append:
            return merge_with
        if isinstance(value, unicode):
            return value + unicode(merge_with)
        else:
            return value + str(merge_with)
