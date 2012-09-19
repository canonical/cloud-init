# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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
import sys

FALL_FORMAT = 'FALLBACK: %(asctime)s - %(filename)s[%(levelname)s]: %(message)s'

Handler = logging.Handler

class QuietStreamHandler(Handler):
    def handleError(self, record):
        pass


class FallbackHandler(Handler):
    def __init__(self, level=logging.NOTSET, fb_handler=None):
        super(FallbackHandler, self).__init__(level)
        if not fb_handler:
            self.fallback_handler = QuietStreamHandler(sys.stderr)
        else:
            self.fallback_handler = fb_handler
        self.fallback_handler.setFormatter(logging.Formatter(FALL_FORMAT))
        self.fallback_handler.setLevel(level)

    def flush(self):
        super(FallbackHandler, self).flush()
        self.fallback_handler.flush()

    def close(self):
        super(FallbackHandler, self).close(self)
        self.fallback_handler.close()

    def setLevel(self, level):
        super(FallbackHandler, self).setLevel(self, level)
        self.fallback_logger.setLevel(level)

    def handleError(self, record):
        try:
            self.fallback_logger.handle(record)
            # Always ensure this one is flushed...
            self.fallback_logger.flush()
        except:
            pass


def _patch_logging():
    # Replace handler with one that will be more
    # tolerant of errors in that it can avoid
    # re-notifying on exceptions and when errors
    # do occur, it can at least try to write to
    # sys.stderr using a fallback logger
    logging.Handler = FallbackHandler


def patch():
    _patch_logging()
