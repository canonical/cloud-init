# This file is part of cloud-init. See LICENSE file for license information.

import glob
import os

from cloudinit import util as c_util
from tests.cloud_tests import (BASE_DIR, TEST_CONF_DIR)

# conf files
CONF_EXT = '.yaml'
VERIFY_EXT = '.py'
PLATFORM_CONF = os.path.join(BASE_DIR, 'platforms.yaml')
RELEASES_CONF = os.path.join(BASE_DIR, 'releases.yaml')
TESTCASE_CONF = os.path.join(BASE_DIR, 'testcases.yaml')


def path_to_name(path):
    """
    convert abs or rel path to test config to path under configs/
    if already a test name, do nothing
    """
    dir_path, file_name = os.path.split(os.path.normpath(path))
    name = os.path.splitext(file_name)[0]
    return os.sep.join((os.path.basename(dir_path), name))


def name_to_path(name):
    """
    convert test config path under configs/ to full config path,
    if already a full path, do nothing
    """
    name = os.path.normpath(name)
    if not name.endswith(CONF_EXT):
        name = name + CONF_EXT
    return name if os.path.isabs(name) else os.path.join(TEST_CONF_DIR, name)


def name_sanatize(name):
    """
    sanatize test name to be used as a module name
    """
    return name.replace('-', '_')


def name_to_module(name):
    """
    convert test name to a loadable module name under testcases/
    """
    name = name_sanatize(path_to_name(name))
    return name.replace(os.path.sep, '.')


def merge_config(base, override):
    """
    merge config and base
    """
    res = base.copy()
    res.update(override)
    res.update({k: merge_config(base.get(k, {}), v)
                for k, v in override.items() if isinstance(v, dict)})
    return res


def load_platform_config(platform):
    """
    load configuration for platform
    """
    main_conf = c_util.read_conf(PLATFORM_CONF)
    return merge_config(main_conf.get('default_platform_config'),
                        main_conf.get('platforms')[platform])


def load_os_config(os_name):
    """
    load configuration for os
    """
    main_conf = c_util.read_conf(RELEASES_CONF)
    return merge_config(main_conf.get('default_release_config'),
                        main_conf.get('releases')[os_name])


def load_test_config(path):
    """
    load a test config file by either abs path or rel path
    """
    return merge_config(c_util.read_conf(TESTCASE_CONF)['base_test_data'],
                        c_util.read_conf(name_to_path(path)))


def list_enabled_platforms():
    """
    list all platforms enabled for testing
    """
    platforms = c_util.read_conf(PLATFORM_CONF).get('platforms')
    return [k for k, v in platforms.items() if v.get('enabled')]


def list_enabled_distros():
    """
    list all distros enabled for testing
    """
    releases = c_util.read_conf(RELEASES_CONF).get('releases')
    return [k for k, v in releases.items() if v.get('enabled')]


def list_test_configs():
    """
    list all available test config files by abspath
    """
    return [os.path.abspath(f) for f in
            glob.glob(os.sep.join((TEST_CONF_DIR, '*', '*.yaml')))]

# vi: ts=4 expandtab
