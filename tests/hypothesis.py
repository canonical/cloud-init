try:
    from hypothesis import given

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

    from unittest import mock

    def given(*_, **__):  # type: ignore
        """Dummy implementation to make pytest collection pass"""

        @mock.Mock  # Add mock to fulfill the expected hypothesis value
        def run_test(item):
            return item

        return run_test


__all__ = ["given", "HAS_HYPOTHESIS"]
