"""Destroy instances in a background thread

interface:

start_reaper()                      - spawns reaper thread
stop_reaper()                       - joins thread and reports leaked instances
reap(instance: IntegrationInstance) - queues instance for deletion

start_reaper() / stop_reaper() - must be called only once
"""

import logging
import queue
import threading
import warnings
from typing import Final, List

from tests.integration_tests.instances import IntegrationInstance

LOG = logging.getLogger()


class Reaper:
    def __init__(self, timeout: float = 30.0):
        # self.timeout sets the amount of time to sleep before retrying
        self.timeout = timeout
        # self.WAKE_REAPER tells the reaper to wake up.
        #
        # A lock is used for synchronization. This means that notify() will
        # block if
        # the reaper is currently awake.
        #
        # It is set by:
        # - signal interrupt indicating cleanup
        # - session completion indicating cleanup
        # - reaped instance indicating work to be done
        self.WAKE_REAPER: Final[threading.Condition] = threading.Condition()

        # self.EXIT_REAPER tells the reaper loop to tear down, called once at
        # end of tests
        self.EXIT_REAPER: Final[threading.Event] = threading.Event()

        # List of instances which temporarily escaped death
        # The primary porpose of the reaper is to coax these instance towards
        # eventual demise and report their insubordination on shutdown.
        self.UNDEAD_LEDGER: Final[List[IntegrationInstance]] = []

        # Queue of newly reaped instances
        self.REAPED_INSTANCES: Final[queue.Queue[IntegrationInstance]] = (
            queue.Queue()
        )

        # Thread object, handle used to re-join the thread
        self.REAPER_THREAD: threading.Thread

    def reap(self, instance: IntegrationInstance):
        """reap() submits an instance to the reaper thread.

        An instance that is passed to the reaper must not be used again. It may
        not be dead yet, but it has no place among the living.
        """
        LOG.info("Reaper: receiving %s", instance.instance.id)
        self.REAPED_INSTANCES.put(instance)
        with self.WAKE_REAPER:
            self.WAKE_REAPER.notify()
            LOG.info("Reaper: awakened to reap")

    def reaper_start(self):
        """Spawn the reaper background thread."""
        LOG.info("Reaper: starting")
        self.REAPER_THREAD = threading.Thread(
            target=self._reaper_loop, name="reaper"
        )
        self.REAPER_THREAD.start()

    def reaper_stop(self):
        """Stop the reaper background thread and wait for completion."""
        LOG.info("Reaper: stopping")
        self.EXIT_REAPER.set()
        with self.WAKE_REAPER:
            self.WAKE_REAPER.notify()
            LOG.info("Reaper: awakened to reap")
        if self.REAPER_THREAD:
            self.REAPER_THREAD.join()
        LOG.info("Reaper: stopped")

    def _destroy(self, instance: IntegrationInstance) -> bool:
        """destroy() destroys an instance and returns True on success."""
        try:
            LOG.info("Reaper: destroying %s", instance.instance.id)
            instance.destroy()
            return True
        except Exception as e:
            LOG.warning(
                "Error while tearing down instance %s: %s ", instance, e
            )
            return False

    def _reaper_loop(self) -> None:
        """reaper_loop() manages all instances that have been reaped

        tasks:
        - destroy newly reaped instances
        - manage a ledger undead instances
        - periodically attempt to kill undead instances
        - die when instructed to
        - ensure that every reaped instance is destroyed at least once before
          reaper dies
        """
        LOG.info("Reaper: exalted in life, to assist others in death")
        while True:
            # nap until woken or timeout
            with self.WAKE_REAPER:
                self.WAKE_REAPER.wait(timeout=self.timeout)
            if self._do_reap():
                break
        LOG.info("Reaper: exited")

    def _do_reap(self) -> bool:
        """_do_reap does a single pass of the reaper loop

        return True if the loop should exit
        """

        new_undead_instances: List[IntegrationInstance] = []

        # first destroy all newly reaped instances
        while not self.REAPED_INSTANCES.empty():
            instance = self.REAPED_INSTANCES.get_nowait()
            success = self._destroy(instance)
            if not success:
                LOG.warning(
                    "Reaper: failed to destroy %s",
                    instance.instance.id,
                )
                # failure to delete, add to the ledger
                new_undead_instances.append(instance)
            else:
                LOG.info("Reaper: destroyed %s", instance.instance.id)

        # every instance has tried at least once and the reaper has been
        # instructed to tear down - so do it
        if self.EXIT_REAPER.is_set():
            if not self.REAPED_INSTANCES.empty():
                # race: an instance was added to the queue after iteration
                # completed. Destroy the latest instance.
                self._update_ledger(new_undead_instances)
                return False
            self._update_ledger(new_undead_instances)
            LOG.info("Reaper: exiting")
            if self.UNDEAD_LEDGER:
                # undead instances exist - unclean teardown
                LOG.info(
                    "Reaper: the faults of incompetent abilities will be "
                    "consigned to oblivion, as myself must soon be to the "
                    "mansions of rest."
                )
                warnings.warn(f"Test instance(s) leaked: {self.UNDEAD_LEDGER}")
            else:
                LOG.info("Reaper: duties complete, my turn to rest")
            return True

        # attempt to destroy all instances which previously refused to
        # destroy
        for instance in self.UNDEAD_LEDGER:
            if self._destroy(instance):
                self.UNDEAD_LEDGER.remove(instance)
                LOG.info("Reaper: destroyed %s (undead)", instance.instance.id)
        self._update_ledger(new_undead_instances)
        return False

    def _update_ledger(self, new_undead_instances: List[IntegrationInstance]):
        """update the ledger with newly undead instances"""
        if new_undead_instances:
            if self.UNDEAD_LEDGER:
                LOG.info(
                    "Reaper: instance(s) not ready to die %s, will now join "
                    "the ranks of the undead: %s",
                    new_undead_instances,
                    self.UNDEAD_LEDGER,
                )
            else:
                LOG.info(
                    "Reaper: instance(s) not ready to die %s",
                    new_undead_instances,
                )
        self.UNDEAD_LEDGER.extend(new_undead_instances)
        return False
