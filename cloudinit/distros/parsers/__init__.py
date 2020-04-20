# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.


def chop_comment(text, comment_chars):
    comment_locations = [text.find(c) for c in comment_chars]
    comment_locations = [c for c in comment_locations if c != -1]
    if not comment_locations:
        return (text, '')
    min_comment = min(comment_locations)
    before_comment = text[0:min_comment]
    comment = text[min_comment:]
    return (before_comment, comment)

# vi: ts=4 expandtab
