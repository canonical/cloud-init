import functools
import time


def retry(*, tries: int = 30, delay: int = 1):
    """Decorator for retries.

    Retry a function until code no longer raises an exception or
    max tries is reached.

    Example:
      @retry(tries=5, delay=1)
      def try_something_that_may_not_be_ready():
          ...
    """

    def _retry(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for _ in range(tries):
                try:
                    func(*args, **kwargs)
                    break
                except Exception as e:
                    last_error = e
                    time.sleep(delay)
            else:
                if last_error:
                    raise last_error

        return wrapper

    return _retry
