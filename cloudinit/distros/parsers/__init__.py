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


def chop_comment(text, comment_chars):
    comment_locations = [text.find(c) for c in comment_chars]
    comment_locations = [c for c in comment_locations if c != -1]
    if not comment_locations:
        return (text, '')
    min_comment = min(comment_locations)
    before_comment = text[0:min_comment]
    comment = text[min_comment:]
    return (before_comment, comment)
