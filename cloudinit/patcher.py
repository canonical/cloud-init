# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import imp
import logging
import sys

# Default fallback format
FALL_FORMAT = ('FALLBACK: %(asctime)s - %(filename)s[%(levelname)s]: ' +
               '%(message)s')


class QuietStreamHandler(logging.StreamHandler):
    def handleError(self, record):
        pass


def _patch_logging():
    # Replace 'handleError' with one that will be more
    # tolerant of errors in that it can avoid
    # re-notifying on exceptions and when errors
    # do occur, it can at least try to write to
    # sys.stderr using a fallback logger
    fallback_handler = QuietStreamHandler(sys.stderr)
    fallback_handler.setFormatter(logging.Formatter(FALL_FORMAT))

    def handleError(self, record):
        try:
            fallback_handler.handle(record)
            fallback_handler.flush()
        except IOError:
            pass
    setattr(logging.Handler, 'handleError', handleError)


def patch():
    imp.acquire_lock()
    try:
        _patch_logging()
    finally:
        imp.release_lock()

# vi: ts=4 expandtab
