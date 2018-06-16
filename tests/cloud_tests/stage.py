# This file is part of cloud-init. See LICENSE file for license information.

"""Stage a run."""

import sys
import time
import traceback

from tests.cloud_tests import LOG


class PlatformComponent(object):
    """Context manager to safely handle platform components."""

    def __init__(self, get_func, preserve_instance=False):
        """Store get_<platform component> function as partial with no args.

        @param get_func: Callable returning an instance from the platform.
        @param preserve_instance: Boolean, when True, do not destroy instance
            after test. Used for test development.
        """
        self.get_func = get_func
        self.preserve_instance = preserve_instance

    def __enter__(self):
        """Create instance of platform component."""
        self.instance = self.get_func()
        return self.instance

    def __exit__(self, etype, value, trace):
        """Destroy instance."""
        if self.instance is not None:
            if self.preserve_instance:
                LOG.info('Preserving test instance %s', self.instance.name)
            else:
                self.instance.destroy()


def run_single(name, call):
    """Run a single function, keeping track of results and time.

    @param name: name of part
    @param call: call to make
    @return_value: a tuple of result and fail count
    """
    res = {
        'name': name,
        'time': 0,
        'errors': [],
        'success': False
    }
    failed = 0
    start_time = time.time()

    try:
        call()
    except Exception as e:
        failed += 1
        res['errors'].append(str(e))
        LOG.error('stage part: %s encountered error: %s', name, str(e))
        trace = traceback.extract_tb(sys.exc_info()[-1])
        LOG.error('traceback:\n%s', ''.join(traceback.format_list(trace)))

    res['time'] = time.time() - start_time
    if failed == 0:
        res['success'] = True

    return res, failed


def run_stage(parent_name, calls, continue_after_error=True):
    """Run a stage of collection, keeping track of results and failures.

    @param parent_name: name of stage calls are under
    @param calls: list of function call taking no params. must return a tuple
                  of results and failures. may raise exceptions
    @param continue_after_error: whether or not to proceed to the next call
                                 after catching an exception or recording a
                                 failure
    @return_value: a tuple of results and failures, with result containing
                   results from the function call under 'stages', and a list
                   of errors (if any on this level), and elapsed time
                   running stage, and the name
    """
    res = {
        'name': parent_name,
        'time': 0,
        'errors': [],
        'stages': [],
        'success': False,
    }
    failed = 0
    start_time = time.time()

    for call in calls:
        try:
            (call_res, call_failed) = call()
            res['stages'].append(call_res)
        except Exception as e:
            call_failed = 1
            res['errors'].append(str(e))
            LOG.error('stage: %s encountered error: %s', parent_name, str(e))
            trace = traceback.extract_tb(sys.exc_info()[-1])
            LOG.error('traceback:\n%s', ''.join(traceback.format_list(trace)))

        failed += call_failed
        if call_failed and not continue_after_error:
            break

    res['time'] = time.time() - start_time
    if not failed:
        res['success'] = True

    return (res, failed)

# vi: ts=4 expandtab
