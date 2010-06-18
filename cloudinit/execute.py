# vi: ts=4 expandtab
#
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
def run(args,cfg,log):
    import subprocess
    import traceback
    try:
        subprocess.check_call(args)
        return
    except subprocess.CalledProcessError as e:
        log.debug(traceback.format_exc(e))
        raise Exception("Cmd returned %s: %s" % ( e.returncode, args ))
    except OSError as e:
        log.debug(traceback.format_exc(e))
        raise Exception("Cmd failed to execute: %s" % ( args ))
