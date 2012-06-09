# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
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


import logging
import logging.handlers
import logging.config

import os
import sys

from StringIO import StringIO

# Logging levels for easy access
CRITICAL = logging.CRITICAL
FATAL = logging.FATAL
ERROR = logging.ERROR
WARNING = logging.WARNING
WARN = logging.WARN
INFO = logging.INFO
DEBUG = logging.DEBUG
NOTSET = logging.NOTSET


class ConsoleFormatter(logging.Formatter):

    def _get_mini_level(self, record):
        if record.levelno in [INFO, NOTSET] or not record.levelname:
            return ''
        lvlname = record.levelname
        return lvlname[0].upper() + ": "

    def format(self, record):
        record.message = record.getMessage()
        rdict = dict(record.__dict__)
        rdict['minilevelname'] = self._get_mini_level(record)
        return self._fmt % (rdict)


def setupLogging(cfg):
    log_cfgs = []
    log_cfg = cfg.get('logcfg')
    if log_cfg:
        # if there is a 'logcfg' entry in the config, respect
        # it, it is the old keyname
        log_cfgs = [log_cfg]
    elif "log_cfgs" in cfg:
        for cfg in cfg['log_cfgs']:
            if isinstance(cfg, list):
                log_cfgs.append('\n'.join(cfg))
            else:
                log_cfgs.append(cfg)

    if not len(log_cfgs):
        sys.stderr.write("Warning, no logging configured\n")
        return

    am_worked = 0
    for logcfg in log_cfgs:
        try:
            if not os.path.isfile(logcfg):
                logcfg = StringIO(logcfg)
            logging.config.fileConfig(logcfg)
            am_worked += 1
        except:
            pass

    if not am_worked:
        sys.stderr.write("Warning, no logging configured\n")


def getLogger(name='cloudinit'):
    return logging.getLogger(name)


# Fixes this annoyance...
# No handlers could be found for logger XXX annoying output...
try:
    from logging import NullHandler
except ImportError:
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass

logger = getLogger()
logger.addHandler(NullHandler())
