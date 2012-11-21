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
    def __init__(self, merger):
        self._merger = merger

    def _on_tuple(self, value, merge_with):
        return self._on_list(list(value), merge_with)

    def _on_list(self, value, merge_with):
        if isinstance(merge_with, (tuple, list)):
            new_value = list(value)
            for m_v in merge_with:
                m_am = 0
                for (i, o_v) in enumerate(new_value):
                    if m_v == o_v:
                        new_value[i] = self._merger.merge(o_v, m_v)
                        m_am += 1
                if m_am == 0:
                    new_value.append(m_v)
        else:
            new_value = list(value)
            new_value.append(merge_with)
        return new_value
