# This file is part of cloud-init. See LICENSE file for license information.

"""Used to collect data from platforms during tests."""

from functools import partial
import os

from cloudinit import util as c_util
from tests.cloud_tests import (config, LOG, setup_image, util)
from tests.cloud_tests.stage import (PlatformComponent, run_stage, run_single)
from tests.cloud_tests import platforms


def collect_script(instance, base_dir, script, script_name):
    """Collect script data.

    @param instance: instance to run script on
    @param base_dir: base directory for output data
    @param script: script contents
    @param script_name: name of script to run
    @return_value: None, may raise errors
    """
    LOG.debug('running collect script: %s', script_name)
    (out, err, exit) = instance.run_script(
        script.encode(), rcs=False,
        description='collect: {}'.format(script_name))
    if err:
        LOG.debug("collect script %s exited '%s' and had stderr: %s",
                  script_name, err, exit)
    if not isinstance(out, bytes):
        raise util.PlatformError(
            "Collection of '%s' returned type %s, expected bytes: %s" %
            (script_name, type(out), out))

    c_util.write_file(os.path.join(base_dir, script_name), out)


def collect_console(instance, base_dir):
    """Collect instance console log.

    @param instance: instance to get console log for
    @param base_dir: directory to write console log to
    """
    logfile = os.path.join(base_dir, 'console.log')
    LOG.debug('getting console log for %s to %s', instance.name, logfile)
    try:
        data = instance.console_log()
    except NotImplementedError as e:
        # args[0] is hacky, but thats all I see to get at the message.
        data = b'NotImplementedError:' + e.args[0].encode()
    with open(logfile, "wb") as fp:
        fp.write(data)


def collect_test_data(args, snapshot, os_name, test_name):
    """Collect data for test case.

    @param args: cmdline arguments
    @param snapshot: instantiated snapshot
    @param test_name: name or path of test to run
    @return_value: tuple of results and fail count
    """
    res = ({}, 1)

    # load test config
    test_name = config.path_to_name(test_name)
    test_config = config.load_test_config(test_name)
    user_data = test_config['cloud_config']
    test_scripts = test_config['collect_scripts']
    test_output_dir = os.sep.join(
        (args.data_dir, snapshot.platform_name, os_name, test_name))

    # if test is not enabled, skip and return 0 failures
    if not test_config.get('enabled', False):
        LOG.warning('test config %s is not enabled, skipping', test_name)
        return ({}, 0)

    # if testcase requires a feature flag that the image does not support,
    # skip the testcase with a warning
    req_features = test_config.get('required_features', [])
    if any(feature not in snapshot.features for feature in req_features):
        LOG.warning('test config %s requires features not supported by image, '
                    'skipping.\nrequired features: %s\nsupported features: %s',
                    test_name, req_features, snapshot.features)
        return ({}, 0)

    # if there are user data overrides required for this test case, apply them
    overrides = snapshot.config.get('user_data_overrides', {})
    if overrides:
        LOG.debug('updating user data for collect with: %s', overrides)
        user_data = util.update_user_data(user_data, overrides)

    # create test instance
    component = PlatformComponent(
        partial(platforms.get_instance, snapshot, user_data,
                block=True, start=False, use_desc=test_name),
        preserve_instance=args.preserve_instance)

    LOG.info('collecting test data for test: %s', test_name)
    with component as instance:
        start_call = partial(run_single, 'boot instance', partial(
            instance.start, wait=True, wait_for_cloud_init=True))
        collect_calls = [partial(run_single, 'script {}'.format(script_name),
                                 partial(collect_script, instance,
                                         test_output_dir, script, script_name))
                         for script_name, script in test_scripts.items()]

        res = run_stage('collect for test: {}'.format(test_name),
                        [start_call] + collect_calls)

        instance.shutdown()
        collect_console(instance, test_output_dir)

    return res


def collect_snapshot(args, image, os_name):
    """Collect data for snapshot of image.

    @param args: cmdline arguments
    @param image: instantiated image with set up complete
    @return_value tuple of results and fail count
    """
    res = ({}, 1)

    component = PlatformComponent(partial(platforms.get_snapshot, image))

    LOG.debug('creating snapshot for %s', os_name)
    with component as snapshot:
        LOG.info('collecting test data for os: %s', os_name)
        res = run_stage(
            'collect test data for {}'.format(os_name),
            [partial(collect_test_data, args, snapshot, os_name, test_name)
             for test_name in args.test_config])

    return res


def collect_image(args, platform, os_name):
    """Collect data for image.

    @param args: cmdline arguments
    @param platform: instantiated platform
    @param os_name: name of distro to collect for
    @return_value: tuple of results and fail count
    """
    res = ({}, 1)

    os_config = config.load_os_config(
        platform.platform_name, os_name, require_enabled=True,
        feature_overrides=args.feature_override)
    LOG.debug('os config: %s', os_config)
    component = PlatformComponent(
        partial(platforms.get_image, platform, os_config))

    LOG.info('acquiring image for os: %s', os_name)
    with component as image:
        res = run_stage('set up and collect data for os: {}'.format(os_name),
                        [partial(setup_image.setup_image, args, image)] +
                        [partial(collect_snapshot, args, image, os_name)],
                        continue_after_error=False)

    return res


def collect_platform(args, platform_name):
    """Collect data for platform.

    @param args: cmdline arguments
    @param platform_name: platform to collect for
    @return_value: tuple of results and fail count
    """
    res = ({}, 1)

    platform_config = config.load_platform_config(
        platform_name, require_enabled=True)
    platform_config['data_dir'] = args.data_dir
    LOG.debug('platform config: %s', platform_config)
    component = PlatformComponent(
        partial(platforms.get_platform, platform_name, platform_config))

    LOG.info('setting up platform: %s', platform_name)
    with component as platform:
        res = run_stage('collect for platform: {}'.format(platform_name),
                        [partial(collect_image, args, platform, os_name)
                         for os_name in args.os_name])

    return res


def collect(args):
    """Entry point for collection.

    @param args: cmdline arguments
    @return_value: fail count
    """
    (res, failed) = run_stage(
        'collect data', [partial(collect_platform, args, platform_name)
                         for platform_name in args.platform])

    LOG.debug('collect stages: %s', res)
    if args.result:
        util.merge_results({'collect_stages': res}, args.result)

    return failed

# vi: ts=4 expandtab
