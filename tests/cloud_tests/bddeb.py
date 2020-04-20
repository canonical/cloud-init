# This file is part of cloud-init. See LICENSE file for license information.

"""Used to build a deb."""

from functools import partial
import os
import tempfile

from cloudinit import util as c_util
from tests.cloud_tests import (config, LOG)
from tests.cloud_tests import platforms
from tests.cloud_tests.stage import (PlatformComponent, run_stage, run_single)

pre_reqs = ['devscripts', 'equivs', 'git', 'tar']


def _out(cmd_res):
    """Get clean output from cmd result."""
    return cmd_res[0].decode("utf-8").strip()


def build_deb(args, instance):
    """Build deb on system and copy out to location at args.deb.

    @param args: cmdline arguments
    @return_value: tuple of results and fail count
    """
    # update remote system package list and install build deps
    LOG.debug('installing pre-reqs')
    pkgs = ' '.join(pre_reqs)
    instance.execute('apt-get update && apt-get install --yes {}'.format(pkgs))

    # local tmpfile that must be deleted
    local_tarball = tempfile.NamedTemporaryFile().name

    # paths to use in remote system
    output_link = '/root/cloud-init_all.deb'
    remote_tarball = _out(instance.execute(['mktemp']))
    extract_dir = '/root'
    bddeb_path = os.path.join(extract_dir, 'packages', 'bddeb')
    git_env = {'GIT_DIR': os.path.join(extract_dir, '.git'),
               'GIT_WORK_TREE': extract_dir}

    LOG.debug('creating tarball of cloud-init at: %s', local_tarball)
    c_util.subp(['tar', 'cf', local_tarball, '--owner', 'root',
                 '--group', 'root', '-C', args.cloud_init, '.'])
    LOG.debug('copying to remote system at: %s', remote_tarball)
    instance.push_file(local_tarball, remote_tarball)

    LOG.debug('extracting tarball in remote system at: %s', extract_dir)
    instance.execute(['tar', 'xf', remote_tarball, '-C', extract_dir])
    instance.execute(['git', 'commit', '-a', '-m', 'tmp', '--allow-empty'],
                     env=git_env)

    LOG.debug('installing deps')
    deps_path = os.path.join(extract_dir, 'tools', 'read-dependencies')
    instance.execute([deps_path, '--install', '--test-distro',
                      '--distro', 'ubuntu', '--python-version', '3'])

    LOG.debug('building deb in remote system at: %s', output_link)
    bddeb_args = args.bddeb_args.split() if args.bddeb_args else []
    instance.execute([bddeb_path, '-d'] + bddeb_args, env=git_env)

    # copy the deb back to the host system
    LOG.debug('copying built deb to host at: %s', args.deb)
    instance.pull_file(output_link, args.deb)


def setup_build(args):
    """Set build system up then run build.

    @param args: cmdline arguments
    @return_value: tuple of results and fail count
    """
    res = ({}, 1)

    # set up platform
    LOG.info('setting up platform: %s', args.build_platform)
    platform_config = config.load_platform_config(args.build_platform)
    platform_call = partial(platforms.get_platform, args.build_platform,
                            platform_config)
    with PlatformComponent(platform_call) as platform:

        # set up image
        LOG.info('acquiring image for os: %s', args.build_os)
        img_conf = config.load_os_config(platform.platform_name, args.build_os)
        image_call = partial(platforms.get_image, platform, img_conf)
        with PlatformComponent(image_call) as image:

            # set up snapshot
            snapshot_call = partial(platforms.get_snapshot, image)
            with PlatformComponent(snapshot_call) as snapshot:

                # create instance with cloud-config to set it up
                LOG.info('creating instance to build deb in')
                empty_cloud_config = "#cloud-config\n{}"
                instance_call = partial(
                    platforms.get_instance, snapshot, empty_cloud_config,
                    use_desc='build cloud-init deb')
                with PlatformComponent(instance_call) as instance:

                    # build the deb
                    res = run_single('build deb on system',
                                     partial(build_deb, args, instance))

    return res


def bddeb(args):
    """Entry point for build deb.

    @param args: cmdline arguments
    @return_value: fail count
    """
    LOG.info('preparing to build cloud-init deb')
    _res, failed = run_stage('build deb', [partial(setup_build, args)])
    return failed

# vi: ts=4 expandtab
