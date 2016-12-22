# This file is part of cloud-init. See LICENSE file for license information.

from tests.cloud_tests import LOG
from tests.cloud_tests import stage, util

from functools import partial
import os


def install_deb(args, image):
    """
    install deb into image
    args: cmdline arguments, must contain --deb
    image: cloud_tests.images instance to operate on
    return_value: None, may raise errors
    """
    # ensure system is compatible with package format
    os_family = util.get_os_family(image.properties['os'])
    if os_family != 'debian':
        raise NotImplementedError('install deb: {} not supported on os '
                                  'family: {}'.format(args.deb, os_family))

    # install deb
    LOG.debug('installing deb: %s into target', args.deb)
    remote_path = os.path.join('/tmp', os.path.basename(args.deb))
    image.push_file(args.deb, remote_path)
    (out, err, exit) = image.execute(['dpkg', '-i', remote_path])
    if exit != 0:
        raise OSError('failed install deb: {}\n\tstdout: {}\n\tstderr: {}'
                      .format(args.deb, out, err))

    # check installed deb version matches package
    fmt = ['-W', "--showformat='${Version}'"]
    (out, err, exit) = image.execute(['dpkg-deb'] + fmt + [remote_path])
    expected_version = out.strip()
    (out, err, exit) = image.execute(['dpkg-query'] + fmt + ['cloud-init'])
    found_version = out.strip()
    if expected_version != found_version:
        raise OSError('install deb version "{}" does not match expected "{}"'
                      .format(found_version, expected_version))

    LOG.debug('successfully installed: %s, version: %s', args.deb,
              found_version)


def install_rpm(args, image):
    """
    install rpm into image
    args: cmdline arguments, must contain --rpm
    image: cloud_tests.images instance to operate on
    return_value: None, may raise errors
    """
    # ensure system is compatible with package format
    os_family = util.get_os_family(image.properties['os'])
    if os_family not in ['redhat', 'sles']:
        raise NotImplementedError('install rpm: {} not supported on os '
                                  'family: {}'.format(args.rpm, os_family))

    # install rpm
    LOG.debug('installing rpm: %s into target', args.rpm)
    remote_path = os.path.join('/tmp', os.path.basename(args.rpm))
    image.push_file(args.rpm, remote_path)
    (out, err, exit) = image.execute(['rpm', '-U', remote_path])
    if exit != 0:
        raise OSError('failed to install rpm: {}\n\tstdout: {}\n\tstderr: {}'
                      .format(args.rpm, out, err))

    fmt = ['--queryformat', '"%{VERSION}"']
    (out, err, exit) = image.execute(['rpm', '-q'] + fmt + [remote_path])
    expected_version = out.strip()
    (out, err, exit) = image.execute(['rpm', '-q'] + fmt + ['cloud-init'])
    found_version = out.strip()
    if expected_version != found_version:
        raise OSError('install rpm version "{}" does not match expected "{}"'
                      .format(found_version, expected_version))

    LOG.debug('successfully installed: %s, version %s', args.rpm,
              found_version)


def upgrade(args, image):
    """
    run the system's upgrade command
    args: cmdline arguments
    image: cloud_tests.images instance to operate on
    return_value: None, may raise errors
    """
    # determine appropriate upgrade command for os_family
    # TODO: maybe use cloudinit.distros for this?
    os_family = util.get_os_family(image.properties['os'])
    if os_family == 'debian':
        cmd = 'apt-get update && apt-get upgrade --yes'
    elif os_family == 'redhat':
        cmd = 'yum upgrade --assumeyes'
    else:
        raise NotImplementedError('upgrade command not configured for distro '
                                  'from family: {}'.format(os_family))

    # upgrade system
    LOG.debug('upgrading system')
    (out, err, exit) = image.execute(['/bin/sh', '-c', cmd])
    if exit != 0:
        raise OSError('failed to upgrade system\n\tstdout: {}\n\tstderr:{}'
                      .format(out, err))


def run_script(args, image):
    """
    run a script in the target image
    args: cmdline arguments, must contain --script
    image: cloud_tests.images instance to operate on
    return_value: None, may raise errors
    """
    # TODO: get exit status back from script and add error handling here
    LOG.debug('running setup image script in target image')
    image.run_script(args.script)


def enable_ppa(args, image):
    """
    enable a ppa in the target image
    args: cmdline arguments, must contain --ppa
    image: cloud_tests.image instance to operate on
    return_value: None, may raise errors
    """
    # ppa only supported on ubuntu (maybe debian?)
    if image.properties['os'] != 'ubuntu':
        raise NotImplementedError('enabling a ppa is only available on ubuntu')

    # add ppa with add-apt-repository and update
    ppa = 'ppa:{}'.format(args.ppa)
    LOG.debug('enabling %s', ppa)
    cmd = 'add-apt-repository --yes {} && apt-get update'.format(ppa)
    (out, err, exit) = image.execute(['/bin/sh', '-c', cmd])
    if exit != 0:
        raise OSError('enable ppa for {} failed\n\tstdout: {}\n\tstderr: {}'
                      .format(ppa, out, err))


def enable_repo(args, image):
    """
    enable a repository in the target image
    args: cmdline arguments, must contain --repo
    image: cloud_tests.image instance to operate on
    return_value: None, may raise errors
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

    LOG.debug('enabling repo: "%s"', args.repo)
    (out, err, exit) = image.execute(['/bin/sh', '-c', cmd])
    if exit != 0:
        raise OSError('enable repo {} failed\n\tstdout: {}\n\tstderr: {}'
                      .format(args.repo, out, err))


def setup_image(args, image):
    """
    set up image as specified in args
    args: cmdline arguments
    image: cloud_tests.image instance to operate on
    return_value: tuple of results and fail count
    """
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
        ('upgrade', upgrade, 'setup func for --upgrade, upgrade pkgs'),
    )

    # determine which setup functions needed
    calls = [partial(stage.run_single, desc, partial(func, args, image))
             for name, func, desc in handlers if getattr(args, name, None)]

    image_name = 'image: distro={}, release={}'.format(
        image.properties['os'], image.properties['release'])
    LOG.info('setting up %s', image_name)
    return stage.run_stage('set up for {}'.format(image_name), calls,
                           continue_after_error=False)

# vi: ts=4 expandtab
