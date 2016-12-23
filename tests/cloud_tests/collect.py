# This file is part of cloud-init. See LICENSE file for license information.

from tests.cloud_tests import (config, LOG, setup_image, util)
from tests.cloud_tests.stage import (PlatformComponent, run_stage, run_single)
from tests.cloud_tests import (platforms, images, snapshots, instances)

from functools import partial
import os


def collect_script(instance, base_dir, script, script_name):
    """
    collect script data
    instance: instance to run script on
    base_dir: base directory for output data
    script: script contents
    script_name: name of script to run
    return_value: None, may raise errors
    """
    LOG.debug('running collect script: %s', script_name)
    util.write_file(os.path.join(base_dir, script_name),
                    instance.run_script(script))


def collect_test_data(args, snapshot, os_name, test_name):
    """
    collect data for test case
    args: cmdline arguments
    snapshot: instantiated snapshot
    test_name: name or path of test to run
    return_value: tuple of results and fail count
    """
    res = ({}, 1)

    # load test config
    test_name = config.path_to_name(test_name)
    test_config = config.load_test_config(test_name)
    user_data = test_config['cloud_config']
    test_scripts = test_config['collect_scripts']
    test_output_dir = os.sep.join(
        (args.data_dir, snapshot.platform_name, os_name, test_name))
    boot_timeout = (test_config.get('boot_timeout')
                    if isinstance(test_config.get('boot_timeout'), int) else
                    snapshot.config.get('timeout'))

    # if test is not enabled, skip and return 0 failures
    if not test_config.get('enabled', False):
        LOG.warn('test config %s is not enabled, skipping', test_name)
        return ({}, 0)

    # create test instance
    component = PlatformComponent(
        partial(instances.get_instance, snapshot, user_data,
                block=True, start=False, use_desc=test_name))

    LOG.info('collecting test data for test: %s', test_name)
    with component as instance:
        start_call = partial(run_single, 'boot instance', partial(
            instance.start, wait=True, wait_time=boot_timeout))
        collect_calls = [partial(run_single, 'script {}'.format(script_name),
                                 partial(collect_script, instance,
                                         test_output_dir, script, script_name))
                         for script_name, script in test_scripts.items()]

        res = run_stage('collect for test: {}'.format(test_name),
                        [start_call] + collect_calls)

    return res


def collect_snapshot(args, image, os_name):
    """
    collect data for snapshot of image
    args: cmdline arguments
    image: instantiated image with set up complete
    return_value tuple of results and fail count
    """
    res = ({}, 1)

    component = PlatformComponent(partial(snapshots.get_snapshot, image))

    LOG.debug('creating snapshot for %s', os_name)
    with component as snapshot:
        LOG.info('collecting test data for os: %s', os_name)
        res = run_stage(
            'collect test data for {}'.format(os_name),
            [partial(collect_test_data, args, snapshot, os_name, test_name)
             for test_name in args.test_config])

    return res


def collect_image(args, platform, os_name):
    """
    collect data for image
    args: cmdline arguments
    platform: instantiated platform
    os_name: name of distro to collect for
    return_value: tuple of results and fail count
    """
    res = ({}, 1)

    os_config = config.load_os_config(os_name)
    if not os_config.get('enabled'):
        raise ValueError('OS {} not enabled'.format(os_name))

    component = PlatformComponent(
        partial(images.get_image, platform, os_config))

    LOG.info('acquiring image for os: %s', os_name)
    with component as image:
        res = run_stage('set up and collect data for os: {}'.format(os_name),
                        [partial(setup_image.setup_image, args, image)] +
                        [partial(collect_snapshot, args, image, os_name)],
                        continue_after_error=False)

    return res


def collect_platform(args, platform_name):
    """
    collect data for platform
    args: cmdline arguments
    platform_name: platform to collect for
    return_value: tuple of results and fail count
    """
    res = ({}, 1)

    platform_config = config.load_platform_config(platform_name)
    if not platform_config.get('enabled'):
        raise ValueError('Platform {} not enabled'.format(platform_name))

    component = PlatformComponent(
        partial(platforms.get_platform, platform_name, platform_config))

    LOG.info('setting up platform: %s', platform_name)
    with component as platform:
        res = run_stage('collect for platform: {}'.format(platform_name),
                        [partial(collect_image, args, platform, os_name)
                         for os_name in args.os_name])

    return res


def collect(args):
    """
    entry point for collection
    args: cmdline arguments
    return_value: fail count
    """
    (res, failed) = run_stage(
        'collect data', [partial(collect_platform, args, platform_name)
                         for platform_name in args.platform])

    LOG.debug('collect stages: %s', res)
    if args.result:
        util.merge_results({'collect_stages': res}, args.result)

    return failed

# vi: ts=4 expandtab
