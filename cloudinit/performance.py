import functools
import logging
import time

LOG = logging.getLogger(__name__)


class Timed:
    """
    A context manager which measures and optionally logs context run time.

    :param msg: A message that describes the thing that is being measured
    :param threshold: Threshold, in seconds. When the context exceeds this
        threshold, a log will be made.
    :param log_mode: Control whether to log. Defaults to "threshold". Possible
        values include:
        "always" - Always log 'msg', even when 'threshold' is not reached.
        "threshold" - Log when context time exceeds 'threshold'.
        "skip" - Do not log. Context time and message are stored in the
            'output' and 'delta' attributes, respectively. Used to manually
            coalesce with other logs at the call site.

    usage:

        this call:
        ```
        with Timed("Configuring the network"):
            run_configure()
        ```

        might produce this log:
        ```
            Configuring the network took 0.100 seconds
        ```
    """

    def __init__(
        self,
        msg: str,
        *,
        threshold: float = 0.01,
        log_mode: str = "threshold",
    ):
        self.msg = msg
        self.threshold = threshold
        self.log_mode = log_mode
        self.output = ""
        self.start = 0.0
        self.delta = 0.0

    def __enter__(self):
        self.start = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.delta = time.monotonic() - self.start
        suffix = f"took {self.delta:.3f} seconds"
        if "always" == self.log_mode:
            LOG.debug("%s %s", self.msg, suffix)
        elif "skip" == self.log_mode:
            return
        elif "threshold" == self.log_mode:
            if self.delta > self.threshold:
                LOG.debug("%s %s", self.msg, suffix)
                self.output = f"{self.msg} {suffix}"
        else:
            raise ValueError(
                f"Invalid Timed log_mode value: '{self.log_mode}'."
            )


def timed(msg: str, *, threshold: float = 0.01, log_mode: str = "threshold"):
    """
    A decorator which measures and optionally logs context run time.

    :param msg: A message that describes the thing that is being measured
    :param threshold: Threshold, in seconds. When the context exceeds this
        threshold, a log will be made.
    :param log_mode: Control whether to log. Defaults to "threshold". Possible
        values include:
        "always" - Always log 'msg', even when 'threshold' is not reached.
        "threshold" - Log when context time exceeds 'threshold'.

    usage:

        this call:
        ```
        @timed("Configuring the network")
        def run_configure():
            ...
        ```

        might produce this log:
        ```
            Configuring the network took 0.100 seconds
        ```
    """

    def wrapper(func):
        @functools.wraps(func)
        def decorator(*args, **kwargs):
            with Timed(msg, threshold=threshold, log_mode=log_mode):
                return func(*args, **kwargs)

        return decorator

    return wrapper
