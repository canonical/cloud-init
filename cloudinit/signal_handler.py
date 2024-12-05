# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
import inspect
import logging
import signal
import sys
from io import StringIO
from typing import Callable, Dict, NamedTuple, Union

from cloudinit import version as vr
from cloudinit.log import log_util

LOG = logging.getLogger(__name__)


class SignalType(NamedTuple):
    message: str
    exit_code: int
    default_signal: Union[Callable, int, None]


def default_handler(_num, _stack) -> None:
    """an empty handler"""
    return None


def get_handler(sig: Union[int, Callable, None]) -> Callable:
    """get_handler gets a callable from signal.signal() output."""
    if callable(sig):
        return sig
    elif sig is None:
        LOG.warning("Signal handler was not installed from Python!")
    elif sig == signal.SIG_DFL:
        LOG.warning("Signal was in unexpected state: SIG_DFL")
    elif sig == signal.SIG_IGN:
        LOG.warning("Signal was in unexpected state: SIG_IGN")
    else:
        LOG.warning(
            "Process signal is in an unknown state: %s(%s)", type(sig), sig
        )
    return default_handler


BACK_FRAME_TRACE_DEPTH = 3
EXIT_FOR: Dict[int, SignalType] = {
    signal.SIGINT: SignalType(
        "Cloud-init %(version)s received SIGINT, exiting...",
        1,
        signal.getsignal(signal.SIGINT),
    ),
    signal.SIGTERM: SignalType(
        "Cloud-init %(version)s received SIGTERM, exiting...",
        1,
        signal.getsignal(signal.SIGTERM),
    ),
    signal.SIGABRT: SignalType(
        "Cloud-init %(version)s received SIGABRT, exiting...",
        1,
        signal.getsignal(signal.SIGABRT),
    ),
}


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
    msg, rc, _ = EXIT_FOR[signum]
    msg = msg % ({"version": vr.version_string()})
    contents = StringIO()
    contents.write("%s\n" % (msg))
    _pprint_frame(frame, 1, BACK_FRAME_TRACE_DEPTH, contents)
    log_util.multi_log(contents.getvalue(), log=LOG, log_level=logging.ERROR)
    sys.exit(rc)


def attach_handlers():
    """attach cloud-init's handlers"""
    sigs_attached = 0
    for signum in EXIT_FOR.keys():
        signal.signal(signum, _handle_exit)
    sigs_attached += len(EXIT_FOR)
    return sigs_attached


def detach_handlers():
    """dettach cloud-init's handlers"""
    sigs_attached = 0
    for number, sig_type in EXIT_FOR.items():
        signal.signal(number, get_handler(sig_type.default_signal))
    sigs_attached += len(EXIT_FOR)
    return sigs_attached
