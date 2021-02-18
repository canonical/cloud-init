# This file is part of cloud-init. See LICENSE file for license information.
import os

from distutils.util import strtobool

##################################################################
# LAUNCH SETTINGS
##################################################################

# Keep instance (mostly for debugging) when test is finished
KEEP_INSTANCE = False
# Keep snapshot image (mostly for debugging) when test is finished
KEEP_IMAGE = False
# Run tests marked as unstable. Expect failures and dragons.
RUN_UNSTABLE = False

# One of:
#  lxd_container
#  lxd_vm
#  azure
#  ec2
#  gce
#  oci
PLATFORM = 'lxd_container'

# The cloud-specific instance type to run. E.g., a1.medium on AWS
# If the pycloudlib instance provides a default, this can be left None
INSTANCE_TYPE = None

# Determines the base image to use or generate new images from.
#
# This can be the name of an Ubuntu release, or in the format
# <image_id>[::<os>[::<release>]].  If given, os and release should describe
# the image specified by image_id.  (Ubuntu releases are converted to this
# format internally; in this case, to "focal::ubuntu::focal".)
OS_IMAGE = 'focal'

# Populate if you want to use a pre-launched instance instead of
# creating a new one. The exact contents will be platform dependent
EXISTING_INSTANCE_ID = None

##################################################################
# IMAGE GENERATION SETTINGS
##################################################################

# Depending on where we are in the development / test / SRU cycle, we'll want
# different methods of getting the source code to our SUT. Because of
# this there are a number of different ways to initialize
# the target environment.

# Can be any of the following:
# NONE
#   Don't modify the target environment at all. This will run
#   cloud-init with whatever code was baked into the image
# IN_PLACE
#   LXD CONTAINER only. Mount the source code as-is directly into
#   the container to override the pre-existing cloudinit module. This
#   won't work for non-local LXD remotes and won't run any installation
#   code.
# PROPOSED
#   Install from the Ubuntu proposed repo
# UPGRADE
#   Upgrade cloud-init to the version in the Ubuntu archive
# <ppa repo>, e.g., ppa:cloud-init-dev/proposed
#   Install from a PPA. It MUST start with 'ppa:'
# <file path>
#   A path to a valid package to be uploaded and installed
CLOUD_INIT_SOURCE = 'NONE'

# Before an instance is torn down, we run `cloud-init collect-logs`
# and transfer them locally. These settings specify when to collect these
# logs and where to put them on the local filesystem
# One of:
#   'ALWAYS'
#   'ON_ERROR'
#   'NEVER'
COLLECT_LOGS = 'ON_ERROR'
LOCAL_LOG_PATH = '/tmp/cloud_init_test_logs'

##################################################################
# SSH KEY SETTINGS
##################################################################

# A path to the public SSH key to use for test runs.  (Defaults to pycloudlib's
# default behaviour, using ~/.ssh/id_rsa.pub.)
PUBLIC_SSH_KEY = None

# For clouds which use named keypairs for SSH connection, the name that is used
# for the keypair.  (Defaults to pycloudlib's default behaviour.)
KEYPAIR_NAME = None

##################################################################
# USER SETTINGS OVERRIDES
##################################################################
# Bring in any user-file defined settings
try:
    # pylint: disable=wildcard-import,unused-wildcard-import
    from tests.integration_tests.user_settings import *  # noqa
except ImportError:
    pass

##################################################################
# ENVIRONMENT SETTINGS OVERRIDES
##################################################################
# Any of the settings in this file can be overridden with an
# environment variable of the same name prepended with CLOUD_INIT_
# E.g., CLOUD_INIT_PLATFORM
# Perhaps a bit too hacky, but it works :)
current_settings = [var for var in locals() if var.isupper()]
for setting in current_settings:
    env_setting = os.getenv(
        'CLOUD_INIT_{}'.format(setting), globals()[setting]
    )
    if isinstance(env_setting, str):
        try:
            env_setting = bool(strtobool(env_setting.strip()))
        except ValueError:
            pass
    globals()[setting] = env_setting
