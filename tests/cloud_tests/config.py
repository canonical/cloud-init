# This file is part of cloud-init. See LICENSE file for license information.

"""Used to setup test configuration."""

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


def get(base, key):
    """Get config entry 'key' from base, ensuring is dictionary."""
    return base[key] if key in base and base[key] is not None else {}


def enabled(config):
    """Test if config item is enabled."""
    return isinstance(config, dict) and config.get('enabled', False)


def path_to_name(path):
    """Convert abs or rel path to test config to path under 'sconfigs/'."""
    dir_path, file_name = os.path.split(os.path.normpath(path))
    name = os.path.splitext(file_name)[0]
    return os.sep.join((os.path.basename(dir_path), name))


def name_to_path(name):
    """Convert test config path under configs/ to full config path."""
    name = os.path.normpath(name)
    if not name.endswith(CONF_EXT):
        name = name + CONF_EXT
    return name if os.path.isabs(name) else os.path.join(TEST_CONF_DIR, name)


def name_sanitize(name):
    """Sanitize test name to be used as a module name."""
    return name.replace('-', '_')


def name_to_module(name):
    """Convert test name to a loadable module name under 'testcases/'."""
    name = name_sanitize(path_to_name(name))
    return name.replace(os.path.sep, '.')


def merge_config(base, override):
    """Merge config and base."""
    res = base.copy()
    res.update(override)
    res.update({k: merge_config(base.get(k, {}), v)
                for k, v in override.items() if isinstance(v, dict)})
    return res


def merge_feature_groups(feature_conf, feature_groups, overrides):
    """Combine feature groups and overrides to construct a supported list.

    @param feature_conf: feature config from releases.yaml
    @param feature_groups: feature groups the release is a member of
    @param overrides: overrides specified by the release's config
    @return_value: dict of {feature: true/false} settings
    """
    res = dict().fromkeys(feature_conf['all'])
    for group in feature_groups:
        res.update(feature_conf['groups'][group])
    res.update(overrides)
    return res


def load_platform_config(platform_name, require_enabled=False):
    """Load configuration for platform.

    @param platform_name: name of platform to retrieve config for
    @param require_enabled: if true, raise error if 'enabled' not True
    @return_value: config dict
    """
    main_conf = c_util.read_conf(PLATFORM_CONF)
    conf = merge_config(main_conf['default_platform_config'],
                        main_conf['platforms'][platform_name])
    if require_enabled and not enabled(conf):
        raise ValueError('Platform is not enabled')
    return conf


def load_os_config(platform_name, os_name, require_enabled=False,
                   feature_overrides=None):
    """Load configuration for os.

    @param platform_name: platform name to load os config for
    @param os_name: name of os to retrieve config for
    @param require_enabled: if true, raise error if 'enabled' not True
    @param feature_overrides: feature flag overrides to merge with features
    @return_value: config dict
    """
    if feature_overrides is None:
        feature_overrides = {}
    main_conf = c_util.read_conf(RELEASES_CONF)
    default = main_conf['default_release_config']
    image = main_conf['releases'][os_name]
    conf = merge_config(merge_config(get(default, 'default'),
                                     get(default, platform_name)),
                        merge_config(get(image, 'default'),
                                     get(image, platform_name)))

    feature_conf = main_conf['features']
    feature_groups = conf.get('feature_groups', [])
    overrides = merge_config(get(conf, 'features'), feature_overrides)
    conf['arch'] = c_util.get_architecture()
    conf['features'] = merge_feature_groups(
        feature_conf, feature_groups, overrides)

    if require_enabled and not enabled(conf):
        raise ValueError('OS is not enabled')
    return conf


def load_test_config(path):
    """Load a test config file by either abs path or rel path."""
    return merge_config(c_util.read_conf(TESTCASE_CONF)['base_test_data'],
                        c_util.read_conf(name_to_path(path)))


def list_feature_flags():
    """List all supported feature flags."""
    feature_conf = get(c_util.read_conf(RELEASES_CONF), 'features')
    return feature_conf.get('all', [])


def list_enabled_platforms():
    """List all platforms enabled for testing."""
    platforms = get(c_util.read_conf(PLATFORM_CONF), 'platforms')
    return [k for k, v in platforms.items() if enabled(v)]


def list_enabled_distros(platforms):
    """List all distros enabled for testing on specified platforms."""
    def platform_has_enabled(config):
        """List if platform is enabled."""
        return any(enabled(merge_config(get(config, 'default'),
                                        get(config, platform)))
                   for platform in platforms)

    releases = get(c_util.read_conf(RELEASES_CONF), 'releases')
    return [k for k, v in releases.items() if platform_has_enabled(v)]


def list_test_configs():
    """List all available test config files by abspath."""
    return [os.path.abspath(f) for f in
            glob.glob(os.sep.join((TEST_CONF_DIR, '*', '*.yaml')))]


ENABLED_PLATFORMS = sorted(list_enabled_platforms())
ENABLED_DISTROS = sorted(list_enabled_distros(ENABLED_PLATFORMS))

# vi: ts=4 expandtab
