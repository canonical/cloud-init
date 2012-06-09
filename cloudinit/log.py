# vim: tabstop=4 shiftwidth=4 softtabstop=4

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
