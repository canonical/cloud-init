"""Defines _Reaper, which destroys instances in a background thread

This class is intended to be a singleton which is instantiated on session setup
and cleaned on session teardown. Any instances submitted to the reaper are
destroyed. Instances that refuse to be destroyed due to external library errors
or flaky infrastructure are tracked, retried and upon test session completion
are reported to the end user as a test warning.
"""

import logging
import queue
import threading
import warnings
from typing import Final, List, Optional

from tests.integration_tests.instances import IntegrationInstance

LOG = logging.getLogger()


class Reaper:
    def __init__(self, timeout: float = 30.0):
        # self.timeout sets the amount of time to sleep before retrying
        self.timeout = timeout
        # self.wake_reaper tells the reaper to wake up.
        #
        # A lock is used for synchronization. This means that notify() will
        # block if
        # the reaper is currently awake.
        #
        # It is set by:
        # - signal interrupt indicating cleanup
        # - session completion indicating cleanup
        # - reaped instance indicating work to be done
        self.wake_reaper: Final[threading.Condition] = threading.Condition()

        # self.exit_reaper tells the reaper loop to tear down, called once at
        # end of tests
        self.exit_reaper: Final[threading.Event] = threading.Event()

        # List of instances which temporarily escaped death
        # The primary purpose of the reaper is to coax these instance towards
        # eventual demise and report their insubordination on shutdown.
        self.undead_ledger: Final[List[IntegrationInstance]] = []

        # Queue of newly reaped instances
        self.reaped_instances: Final[queue.Queue[IntegrationInstance]] = (
            queue.Queue()
        )

        # Thread object, handle used to re-join the thread
        self.reaper_thread: Optional[threading.Thread] = None

        # Count the dead
        self.counter = 0

    def reap(self, instance: IntegrationInstance):
        """reap() submits an instance to the reaper thread.

        An instance that is passed to the reaper must not be used again. It may
        not be dead yet, but it has no place among the living.
        """
        LOG.info("Reaper: receiving %s", instance.instance.id)

        self.reaped_instances.put(instance)
        with self.wake_reaper:
            self.wake_reaper.notify()
            LOG.info("Reaper: awakened to reap")

    def start(self):
        """Spawn the reaper background thread."""
        LOG.info("Reaper: starting")
        self.reaper_thread = threading.Thread(
            target=self._reaper_loop, name="reaper"
        )
        self.reaper_thread.start()

    def stop(self):
        """Stop the reaper background thread and wait for completion."""
        LOG.info("Reaper: stopping")
        self.exit_reaper.set()
        with self.wake_reaper:
            self.wake_reaper.notify()
            LOG.info("Reaper: awakened to reap")
        if self.reaper_thread and self.reaper_thread.is_alive():
            self.reaper_thread.join()
        LOG.info("Reaper: stopped")

    def _destroy(self, instance: IntegrationInstance) -> bool:
        """destroy() destroys an instance and returns True on success."""
        try:
            LOG.info("Reaper: destroying %s", instance.instance.id)
            instance.destroy()
            self.counter += 1
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
            with self.wake_reaper:
                self.wake_reaper.wait(timeout=self.timeout)
            if self._do_reap():
                break
        LOG.info("Reaper: exited")

    def _do_reap(self) -> bool:
        """_do_reap does a single pass of the reaper loop

        return True if the loop should exit
        """

        new_undead_instances: List[IntegrationInstance] = []

        # first destroy all newly reaped instances
        while not self.reaped_instances.empty():
            instance = self.reaped_instances.get_nowait()
            instance_id = instance.instance.id
            success = self._destroy(instance)
            if not success:
                LOG.warning(
                    "Reaper: failed to destroy %s",
                    instance.instance.id,
                )
                # failure to delete, add to the ledger
                new_undead_instances.append(instance)
            else:
                LOG.info("Reaper: destroyed %s", instance_id)

        # every instance has tried at least once and the reaper has been
        # instructed to tear down - so do it
        if self.exit_reaper.is_set():
            if not self.reaped_instances.empty():
                # race: an instance was added to the queue after iteration
                # completed. Destroy the latest instance.
                self._update_undead_ledger(new_undead_instances)
                return False
            self._update_undead_ledger(new_undead_instances)
            LOG.info("Reaper: exiting")
            if self.undead_ledger:
                # undead instances exist - unclean teardown
                LOG.info(
                    "Reaper: the faults of incompetent abilities will be "
                    "consigned to oblivion, as myself must soon be to the "
                    "mansions of rest."
                )
                warnings.warn(f"Test instance(s) leaked: {self.undead_ledger}")
            else:
                LOG.info("Reaper: duties complete, my turn to rest")
            LOG.info(
                "Reaper: reaped %s/%s instances",
                self.counter,
                self.counter + len(self.undead_ledger),
            )
            return True

        # attempt to destroy all instances which previously refused to destroy
        for instance in self.undead_ledger:
            if self.exit_reaper.is_set() and self.reaped_instances.empty():
                # don't retry instances if the exit_reaper Event is set
                break
            instance_id = instance.instance.id
            if self._destroy(instance):
                self.undead_ledger.remove(instance)
                LOG.info("Reaper: destroyed %s (undead)", instance_id)

        self._update_undead_ledger(new_undead_instances)
        return False

    def _update_undead_ledger(
        self, new_undead_instances: List[IntegrationInstance]
    ):
        """update the ledger with newly undead instances"""
        if new_undead_instances:
            if self.undead_ledger:
                LOG.info(
                    "Reaper: instance(s) not ready to die %s, will now join "
                    "the ranks of the undead: %s",
                    new_undead_instances,
                    self.undead_ledger,
                )
            else:
                LOG.info(
                    "Reaper: instance(s) not ready to die %s",
                    new_undead_instances,
                )
        self.undead_ledger.extend(new_undead_instances)
        return False
