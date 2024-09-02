import logging
import os
import sys

from cloudinit.performance import timed

LOG = logging.getLogger(__name__)


def logexc(
    log, msg, *args, log_level: int = logging.WARNING, exc_info=True
) -> None:
    log.log(log_level, msg, *args)
    log.debug(msg, exc_info=exc_info, *args)


@timed("Writing to console")
def write_to_console(conpath, text):
    with open(conpath, "w") as wfh:
        wfh.write(text)
        wfh.flush()


def multi_log(
    text,
    console=True,
    stderr=True,
    log=None,
    log_level=logging.DEBUG,
    fallback_to_stdout=True,
):
    if stderr:
        sys.stderr.write(text)
    if console:
        conpath = "/dev/console"
        writing_to_console_worked = False
        if os.path.exists(conpath):
            try:
                write_to_console(conpath, text)
                writing_to_console_worked = True
            except OSError:
                console_error = "Failed to write to /dev/console"
                sys.stdout.write(f"{console_error}\n")
                if log:
                    log.log(logging.WARNING, console_error)

        if fallback_to_stdout and not writing_to_console_worked:
            # A container may lack /dev/console (arguably a container bug).
            # Additionally, /dev/console may not be writable to on a VM (again
            # likely a VM bug or virtualization bug).
            #
            # If either of these is the case, then write output to stdout.
            # This will result in duplicate stderr and stdout messages if
            # stderr was True.
            #
            # even though systemd might have set up output to go to
            # /dev/console, the user may have configured elsewhere via
            # cloud-config 'output'.  If there is /dev/console, messages will
            # still get there.
            sys.stdout.write(text)
    if log:
        if text[-1] == "\n":
            log.log(log_level, text[:-1])
        else:
            log.log(log_level, text)


def error(msg, rc=1, fmt="Error:\n{}", sys_exit=False):
    r"""Print error to stderr and return or exit

    @param msg: message to print
    @param rc: return code (default: 1)
    @param fmt: format string for putting message in (default: 'Error:\n {}')
    @param sys_exit: exit when called (default: false)
    """
    print(fmt.format(msg), file=sys.stderr)
    if sys_exit:
        sys.exit(rc)
    return rc
