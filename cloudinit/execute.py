#    Copyright (C) 2009-2010 Canonical Ltd.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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
def run(list,cfg):
    import subprocess
    retcode = subprocess.call(list)

    if retcode == 0:
        return

    if retcode < 0:
        str="Cmd terminated by signal %s\n" % -retcode
    else:
        str="Cmd returned %s\n" % retcode
    str+=' '.join(list)
    raise Exception(str)
