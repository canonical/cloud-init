# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
import contextlib
import inspect
import logging
import signal
import sys
import threading
import types
from io import StringIO
from typing import Callable, Dict, Final, NamedTuple, Union

from cloudinit import version as vr
from cloudinit.log import log_util

LOG = logging.getLogger(__name__)

SIG_MESSAGE: Final = "Cloud-init {} received {}, exiting\n"
BACK_FRAME_TRACE_DEPTH: Final = 3
SIGNALS: Final[Dict[int, str]] = {
    signal.SIGINT: "Cloud-init %(version)s received SIGINT, exiting",
    signal.SIGTERM: "Cloud-init %(version)s received SIGTERM, exiting",
    signal.SIGABRT: "Cloud-init %(version)s received SIGABRT, exiting",
}


class ExitBehavior(NamedTuple):
    exit_code: int
    log_level: int


SIGNAL_EXIT_BEHAVIOR_CRASH: Final = ExitBehavior(1, logging.ERROR)
SIGNAL_EXIT_BEHAVIOR_QUIET: Final = ExitBehavior(0, logging.INFO)
_SIGNAL_EXIT_BEHAVIOR = SIGNAL_EXIT_BEHAVIOR_CRASH
_SUSPEND_WRITE_LOCK = threading.RLock()


def inspect_handler(sig: Union[int, Callable, None]) -> None:
    """inspect_handler() logs signal handler state"""
    if callable(sig):
        # only produce a log when the signal handler isn't in the expected
        # default state
        if not isinstance(sig, types.BuiltinFunctionType):
            LOG.info("Signal state [%s] - previously custom handler.", sig)
    elif sig == signal.SIG_IGN:
        LOG.info("Signal state [SIG_IGN] - previously ignored.")
    elif sig is None:
        LOG.info("Signal state [None] - previously not installed from Python.")
    elif sig == signal.SIG_DFL:
        LOG.info(
            "Signal state [%s] - default way of handling signal was "
            "previously in use.",
            sig,
        )
    else:
        # this should never happen, unless something in Python changes
        # https://docs.python.org/3/library/signal.html#signal.getsignal
        LOG.warning("Signal state [%s(%s)] - unknown", type(sig), sig)


def _pprint_frame(frame, depth, max_depth, contents):
    if depth > max_depth or not frame:
        return
    frame_info = inspect.getframeinfo(frame)
    prefix = " " * (depth * 2)
    contents.write("%sFilename: %s\n" % (prefix, frame_info.filename))
    contents.write("%sFunction: %s\n" % (prefix, frame_info.function))
    contents.write("%sLine number: %s\n" % (prefix, frame_info.lineno))
    _pprint_frame(frame.f_back, depth + 1, max_depth, contents)


def _handle_exit(signum, frame):
    # in practice we always receive a Signals object but int is possible
    name = signum.name if isinstance(signum, signal.Signals) else signum
    contents = StringIO(SIG_MESSAGE.format(vr.version_string(), name))
    _pprint_frame(frame, 1, BACK_FRAME_TRACE_DEPTH, contents)
    log_util.multi_log(
        contents.getvalue(), log=LOG, log_level=_SIGNAL_EXIT_BEHAVIOR.log_level
    )
    sys.exit(_SIGNAL_EXIT_BEHAVIOR.exit_code)


def attach_handlers():
    """attach cloud-init's handlers"""
    sigs_attached = 0
    for signum in SIGNALS.keys():
        inspect_handler(signal.signal(signum, _handle_exit))
    sigs_attached += len(SIGNALS)
    return sigs_attached


@contextlib.contextmanager
def suspend_crash():
    """suspend_crash() allows signals to be received without exiting 1

    This allow signal handling without a crash where it is expected. The
    call stack is still printed if signal is received during this context, but
    the return code is 0 and no traceback is printed.

    Threadsafe.
    """
    global _SIGNAL_EXIT_BEHAVIOR

    # If multiple threads simultaneously were to modify this
    # global state, this function would not behave as expected.
    with _SUSPEND_WRITE_LOCK:
        _SIGNAL_EXIT_BEHAVIOR = SIGNAL_EXIT_BEHAVIOR_QUIET
        yield
        _SIGNAL_EXIT_BEHAVIOR = SIGNAL_EXIT_BEHAVIOR_CRASH
