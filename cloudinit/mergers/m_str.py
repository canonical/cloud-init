# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.


class Merger:
    def __init__(self, _merger, opts):
        self._append = "append" in opts

    def __str__(self):
        return "StringMerger: (append=%s)" % (self._append)

    # On encountering a unicode object to merge value with
    # we will for now just proxy into the string method to let it handle it.
    def _on_unicode(self, value, merge_with):
        return self._on_str(value, merge_with)

    # On encountering a string object to merge with we will
    # perform the following action, if appending we will
    # merge them together, otherwise we will just return value.
    def _on_str(self, value, merge_with):
        if not isinstance(value, str):
            return merge_with
        if not self._append:
            return merge_with
        return value + merge_with


# vi: ts=4 expandtab
