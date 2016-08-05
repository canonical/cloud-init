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

__VERSION__ = "0.7.6"
__EXPORT_VERSION__ = "@@EXPORT_VERSION@@"


def version_string():
    if not __EXPORT_VERSION__.startswith("@@"):
        return __EXPORT_VERSION__
    return __VERSION__


def full_version_string():
    if __EXPORT_VERSION__.startswith("@@"):
        raise ValueError("No full version available")
    return __EXPORT_VERSION__
