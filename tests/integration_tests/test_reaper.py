"""reaper self-test"""

import logging
import time
import warnings
from unittest import mock

import pytest

from tests.integration_tests import reaper
from tests.integration_tests.instances import IntegrationInstance

LOG = logging.Logger(__name__)


class MockInstance(IntegrationInstance):
    # because of instance id printing
    instance = mock.Mock()

    def __init__(self, times_refused):
        self.times_refused = times_refused
        self.call_count = 0

        # assert that destruction succeeded
        self.stopped = False

    def destroy(self):
        """destroy() only succeeds after failing N=times_refused times"""
        if self.call_count == self.times_refused:
            self.stopped = True
            return
        self.call_count += 1
        raise RuntimeError("I object!")


@pytest.mark.ci
class TestReaper:
    def test_start_stop(self):
        """basic setup teardown"""

        instance = MockInstance(0)
        r = reaper._Reaper()
        # start / stop
        r.start()
        r.stop()
        # start / reap / stop
        r.start()
        r.reap(instance)
        r.stop()

        # start / stop
        r.start()
        r.stop()
        assert instance.stopped

    def test_basic_reap(self):
        """basic setup teardown"""

        i_1 = MockInstance(0)
        r = reaper._Reaper()
        r.start()
        r.reap(i_1)
        r.stop()
        assert i_1.stopped

    def test_unreaped_instance(self):
        """a single warning should print for any number of leaked instances"""

        i_1 = MockInstance(64)
        i_2 = MockInstance(64)
        r = reaper._Reaper()
        r.start()
        r.reap(i_1)
        r.reap(i_2)
        with warnings.catch_warnings(record=True) as w:
            r.stop()
        assert len(w) == 1

    def test_stubborn_reap(self):
        """verify that stubborn instances are cleaned"""

        sleep_time = 0.000_001
        sleep_total = 0.0
        instances = [
            MockInstance(0),
            MockInstance(3),
            MockInstance(6),
            MockInstance(9),
            MockInstance(12),
            MockInstance(9),
            MockInstance(6),
            MockInstance(3),
            MockInstance(0),
        ]

        # forcibly disallow sleeping, to avoid wasted time during tests
        r = reaper._Reaper(timeout=0.0)
        r.start()
        for i in instances:
            r.reap(i)

        # this should really take no time at all, waiting 1s should be plenty
        # of time for the reaper to reap it when not sleeping
        while sleep_total < 1.0:
            # are any still undead?
            any_undead = False
            for i in instances:
                if not i.stopped:
                    any_undead = True
                    break
            if not any_undead:
                # test passed
                # Advance to GO, collect $400
                break
            # sleep then recheck, incremental backoff
            sleep_total += sleep_time
            sleep_time *= 2
            time.sleep(sleep_time)
        r.stop()
        for i in instances:
            assert i.stopped, (
                f"Reaper didn't reap stubborn instance {i} in {sleep_total}s. "
                "Something appears to be broken in the reaper logic or test."
            )

    def test_start_stop_multiple(self):
        """reap lots of instances

        obedient ones
        """
        num = 64
        instances = []
        r = reaper._Reaper()
        r.start()
        for _ in range(num):
            i = MockInstance(0)
            instances.append(i)
            r.reap(i)
        r.stop()
        for i in instances:
            assert i.stopped
