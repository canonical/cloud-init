import logging
import queue
import threading
from functools import partial
from typing import List, Final

import pytest

from tests.integration_tests.instances import IntegrationInstance

LOG = logging.getLogger()

# Thread object, handle used to re-join the thread
REAPER_THREAD: threading.Thread

# A queue of newly reaped instances
REAPED_INSTANCES: Final[queue.Queue[IntegrationInstance]] = queue.Queue()

# START_REAPER triggers re-running the loop
START_REAPER: Final[threading.Condition] = threading.Condition()

# EXIT_REAPER tells the reaper loop to tear down, called once at end of tests
EXIT_REAPER: Final[threading.Event] = threading.Event()

# A list of instances which temporarily escaped death
# The primary porpose of the reaper is to coax these instance towards
# eventual demise and report their insubordination on shutdown.
UNDEAD_LEDGER: List[IntegrationInstance]


def reap(instance: IntegrationInstance):
    """reap() submits an instance to the reaper thread.

    An instance that is passed to the reaper must not be used again. It may
    not be dead yet, but it has no place among the living.
    """
    LOG.info("Instance %s submitted to reaper.", instance.instance.id)
    REAPED_INSTANCES.put(instance)
    START_REAPER.notify()


def reaper_start():
    """Spawn the reaper background thread."""
    global REAPER_THREAD
    REAPER_THREAD = threading.Thread(target=reaper_loop, name="instance reaper")

def reaper_stop():
    """Stop the reaper background thread."""
    EXIT_REAPER.set()
    if REAPER_THREAD:
        REAPER_THREAD.join()

def destroy(instance: IntegrationInstance) -> bool:
    """destroy() destroys an instance and returns True on success."""
    try:
        instance.destroy()
        return True
    except Exception as e:
        LOG.warning("Error while tearing down instance %s: %s ", instance, e)
        return False


def reaper_loop():
    """reaper_loop() manages all instances that have been reaped

    Newly reaped instances are destroyed
    A ledger of the undead is managed (and previous failures retried).
    """
    global UNDEAD_LEDGER
    LOG.info("[reaper] exhalted in life, to assist others in death")
    while START_REAPER.wait(timeout=30.0):
        new_undead_instances = []

        # first destroy all newly reaped instances
        if not REAPED_INSTANCES.empty():
            for instance in iter(
                partial(REAPED_INSTANCES.get, block=False), None
            ):
                success = destroy(instance)
                if not success:
                    LOG.warning(
                        "Reaper could not destroy instance %s. "
                        "It is now undead.",
                        instance.instance.id,
                    )
                    # failure to delete, put in on the background thread
                    new_undead_instances.append(instance)
                else:
                    LOG.info(
                        "Reaper destroyed instance %s.", instance.instance.id
                    )
        # every instance has tried at least once and the reaper has been
        # instructed too tear down - so do it
        if EXIT_REAPER.isSet():
            if not REAPED_INSTANCES.empty():
                # race: an instance was added to the queue after iteration
                # completed. Destroy the latest instance.
                continue
            elif UNDEAD_LEDGER:
                # undead instances exist - unclean teardown
                LOG.info(
                    "[reaper] the faults of incompetent abilities will be "
                    "consigned to oblivion, as myself must soon be to the "
                    "mansions of rest."
                )
                pytest.exit(
                    f"Unable to reap instances: {UNDEAD_LEDGER}",
                    returncode=2
                )
            else:
                LOG.info("[reaper] duties complete, my turn to rest")
                return

        # attempt to destroy all instances which previously refused to destroy
        for instance in UNDEAD_LEDGER:
            success = destroy(instance)
            if not success:
                # if unreaped then put it back in the list
                new_undead_instances.append(instance)
            else:
                LOG.info(
                    "Reaper killed undead instance: %s", instance.instance.id
                )
        # update the list with remaining instances
        UNDEAD_LEDGER = new_undead_instances
