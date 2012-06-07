# vim: tabstop=4 shiftwidth=4 softtabstop=4

import logging
import logging.handlers
import sys

# Logging levels for easy access
CRITICAL = logging.CRITICAL
FATAL = logging.FATAL
ERROR = logging.ERROR
WARNING = logging.WARNING
WARN = logging.WARN
INFO = logging.INFO
DEBUG = logging.DEBUG
NOTSET = logging.NOTSET

# File log rotation settings
ROTATE_AMOUNT = 10  # Only keep the past 9 + 1 active
ROTATE_SIZE = 10 * 1024 * 1024  # 10 MB


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
        # Skipping exception info for the console...
        return self._fmt % (rdict)


def setupLogging(level, filename=None, filelevel=logging.DEBUG):
    root = getLogger()
    consolelg = logging.StreamHandler(sys.stdout)
    consolelg.setFormatter(ConsoleFormatter('%(minilevelname)s%(message)s'))
    consolelg.setLevel(level)
    root.addHandler(consolelg)
    if filename:
        filelg = logging.handlers.RotatingFileHandler(filename, maxBytes=ROTATE_SIZE, backupCount=ROTATE_AMOUNT)
        filelg.setFormatter(logging.Formatter('%(levelname)s: @%(name)s : %(message)s'))
        filelg.setLevel(filelevel)
        root.addHandler(filelg)
    root.setLevel(level)


def logging_set_from_cfg(cfg):
    log_cfgs = []
    logcfg = util.get_cfg_option_str(cfg, "log_cfg", False)
    if logcfg:
        # if there is a 'logcfg' entry in the config, respect
        # it, it is the old keyname
        log_cfgs = [logcfg]
    elif "log_cfgs" in cfg:
        for cfg in cfg['log_cfgs']:
            if isinstance(cfg, list):
                log_cfgs.append('\n'.join(cfg))
            else:
                log_cfgs.append()

    if not len(log_cfgs):
        sys.stderr.write("Warning, no logging configured\n")
        return

    for logcfg in log_cfgs:
        try:
            logging.config.fileConfig(StringIO.StringIO(logcfg))
            return
        except:
            pass

    raise Exception("no valid logging found\n")


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
