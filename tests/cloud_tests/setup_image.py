# This file is part of cloud-init. See LICENSE file for license information.

"""Setup image for testing."""

from functools import partial
import os
import yaml

from tests.cloud_tests import LOG
from tests.cloud_tests import stage, util


def installed_package_version(image, package, ensure_installed=True):
    """Get installed version of package.

    @param image: cloud_tests.images instance to operate on
    @param package: name of package
    @param ensure_installed: raise error if not installed
    @return_value: cloud-init version string
    """
    os_family = util.get_os_family(image.properties['os'])
    if os_family == 'debian':
        cmd = ['dpkg-query', '-W', "--showformat=${Version}", package]
    elif os_family == 'redhat':
        cmd = ['rpm', '-q', '--queryformat', "'%{VERSION}'", package]
    else:
        raise NotImplementedError

    return image.execute(
        cmd, description='query version for package: {}'.format(package),
        rcs=(0,) if ensure_installed else range(0, 256))[0].strip()


def install_deb(args, image):
    """Install deb into image.

    @param args: cmdline arguments, must contain --deb
    @param image: cloud_tests.images instance to operate on
    @return_value: None, may raise errors
    """
    # ensure system is compatible with package format
    os_family = util.get_os_family(image.properties['os'])
    if os_family != 'debian':
        raise NotImplementedError('install deb: {} not supported on os '
                                  'family: {}'.format(args.deb, os_family))

    # install deb
    msg = 'install deb: "{}" into target'.format(args.deb)
    LOG.debug(msg)
    remote_path = os.path.join('/tmp', os.path.basename(args.deb))
    image.push_file(args.deb, remote_path)
    image.execute(
        ['apt-get', 'install', '--allow-downgrades', '--assume-yes',
         remote_path], description=msg)
    # check installed deb version matches package
    fmt = ['-W', "--showformat=${Version}"]
    out = image.execute(['dpkg-deb'] + fmt + [remote_path])[0]
    expected_version = out.strip()
    found_version = installed_package_version(image, 'cloud-init')
    if expected_version != found_version:
        raise OSError('install deb version "{}" does not match expected "{}"'
                      .format(found_version, expected_version))

    LOG.debug('successfully installed: %s, version: %s', args.deb,
              found_version)


def install_rpm(args, image):
    """Install rpm into image.

    @param args: cmdline arguments, must contain --rpm
    @param image: cloud_tests.images instance to operate on
    @return_value: None, may raise errors
    """
    os_family = util.get_os_family(image.properties['os'])
    if os_family != 'redhat':
        raise NotImplementedError('install rpm: {} not supported on os '
                                  'family: {}'.format(args.rpm, os_family))

    # install rpm
    msg = 'install rpm: "{}" into target'.format(args.rpm)
    LOG.debug(msg)
    remote_path = os.path.join('/tmp', os.path.basename(args.rpm))
    image.push_file(args.rpm, remote_path)
    image.execute(['rpm', '-U', remote_path], description=msg)

    fmt = ['--queryformat', '"%{VERSION}"']
    (out, _err, _exit) = image.execute(['rpm', '-q'] + fmt + [remote_path])
    expected_version = out.strip()
    found_version = installed_package_version(image, 'cloud-init')
    if expected_version != found_version:
        raise OSError('install rpm version "{}" does not match expected "{}"'
                      .format(found_version, expected_version))

    LOG.debug('successfully installed: %s, version %s', args.rpm,
              found_version)


def upgrade(args, image):
    """Upgrade or install cloud-init from repo.

    @param args: cmdline arguments
    @param image: cloud_tests.images instance to operate on
    @return_value: None, may raise errors
    """
    os_family = util.get_os_family(image.properties['os'])
    if os_family == 'debian':
        cmd = 'apt-get update && apt-get install cloud-init --yes'
    elif os_family == 'redhat':
        cmd = 'sleep 10 && yum install cloud-init --assumeyes'
    else:
        raise NotImplementedError

    msg = 'upgrading cloud-init'
    LOG.debug(msg)
    image.execute(cmd, description=msg)


def upgrade_full(args, image):
    """Run the system's full upgrade command.

    @param args: cmdline arguments
    @param image: cloud_tests.images instance to operate on
    @return_value: None, may raise errors
    """
    os_family = util.get_os_family(image.properties['os'])
    if os_family == 'debian':
        cmd = 'apt-get update && apt-get upgrade --yes'
    elif os_family == 'redhat':
        cmd = 'yum upgrade --assumeyes'
    else:
        raise NotImplementedError('upgrade command not configured for distro '
                                  'from family: {}'.format(os_family))

    msg = 'full system upgrade'
    LOG.debug(msg)
    image.execute(cmd, description=msg)


def run_script(args, image):
    """Run a script in the target image.

    @param args: cmdline arguments, must contain --script
    @param image: cloud_tests.images instance to operate on
    @return_value: None, may raise errors
    """
    msg = 'run setup image script in target image'
    LOG.debug(msg)
    image.run_script(args.script, description=msg)


def enable_ppa(args, image):
    """Enable a ppa in the target image.

    @param args: cmdline arguments, must contain --ppa
    @param image: cloud_tests.image instance to operate on
    @return_value: None, may raise errors
    """
    # ppa only supported on ubuntu (maybe debian?)
    if image.properties['os'].lower() != 'ubuntu':
        raise NotImplementedError('enabling a ppa is only available on ubuntu')

    # add ppa with add-apt-repository and update
    ppa = 'ppa:{}'.format(args.ppa)
    msg = 'enable ppa: "{}" in target'.format(ppa)
    LOG.debug(msg)
    cmd = 'add-apt-repository --yes {} && apt-get update'.format(ppa)
    image.execute(cmd, description=msg)


def enable_repo(args, image):
    """Enable a repository in the target image.

    @param args: cmdline arguments, must contain --repo
    @param image: cloud_tests.image instance to operate on
    @return_value: None, may raise errors
    """
    # find enable repo command for the distro
    os_family = util.get_os_family(image.properties['os'])
    if os_family == 'debian':
        cmd = ('echo "{}" >> "/etc/apt/sources.list" '.format(args.repo) +
               '&& apt-get update')
    elif os_family == 'centos':
        cmd = 'yum-config-manager --add-repo="{}"'.format(args.repo)
    else:
        raise NotImplementedError('enable repo command not configured for '
                                  'distro from family: {}'.format(os_family))

    msg = 'enable repo: "{}" in target'.format(args.repo)
    LOG.debug(msg)
    image.execute(cmd, description=msg)


def setup_image(args, image):
    """Set up image as specified in args.

    @param args: cmdline arguments
    @param image: cloud_tests.image instance to operate on
    @return_value: tuple of results and fail count
    """
    # update the args if necessary for this image
    overrides = image.setup_overrides
    LOG.debug('updating args for setup with: %s', overrides)
    args = util.update_args(args, overrides, preserve_old=True)

    # mapping of setup cmdline arg name to setup function
    # represented as a tuple rather than a dict or odict as lookup by name not
    # needed, and order is important as --script and --upgrade go at the end
    handlers = (
        # arg   handler     description
        ('deb', install_deb, 'setup func for --deb, install deb'),
        ('rpm', install_rpm, 'setup func for --rpm, install rpm'),
        ('repo', enable_repo, 'setup func for --repo, enable repo'),
        ('ppa', enable_ppa, 'setup func for --ppa, enable ppa'),
        ('script', run_script, 'setup func for --script, run script'),
        ('upgrade', upgrade, 'setup func for --upgrade, upgrade cloud-init'),
        ('upgrade-full', upgrade_full, 'setup func for --upgrade-full'),
    )

    # determine which setup functions needed
    calls = [partial(stage.run_single, desc, partial(func, args, image))
             for name, func, desc in handlers if getattr(args, name, None)]

    try:
        data = yaml.load(image.read_data("/etc/cloud/build.info", decode=True))
        info = ' '.join(["%s=%s" % (k, data.get(k))
                         for k in ("build_name", "serial") if k in data])
    except Exception as e:
        info = "N/A (%s)" % e

    LOG.info('setting up %s (%s)', image, info)
    res = stage.run_stage(
        'set up for {}'.format(image), calls, continue_after_error=False)
    return res

# vi: ts=4 expandtab
