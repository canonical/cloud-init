# This file is part of cloud-init. See LICENSE file for license information.
"""
Feature flags are used as a way to easily toggle configuration
**at build time**. They are provided to accommodate feature deprecation and
downstream configuration changes.

Currently used upstream values for feature flags are set in
``cloudinit/features.py``. Overrides to these values (typically via quilt
patch) can be placed
in a file called ``feature_overrides.py`` in the same directory. Any value
set in ``feature_overrides.py`` will override the original value set
in ``features.py``.

Each flag should include a short comment regarding the reason for
the flag and intended lifetime.

Tests are required for new feature flags, and tests must verify
all valid states of a flag, not just the default state.
"""

ERROR_ON_USER_DATA_FAILURE = True
"""
If there is a failure in obtaining user data (i.e., #include or
decompress fails), old behavior is to log a warning and proceed.
After the 20.2 release, we instead raise an exception.
This flag can be removed after Focal is no longer supported
"""


ALLOW_EC2_MIRRORS_ON_NON_AWS_INSTANCE_TYPES = False
"""
When configuring apt mirrors, old behavior is to allow
the use of ec2 mirrors if the datasource availability_zone format
matches one of the possible aws ec2 regions. After the 20.2 release, we
no longer publish ec2 region mirror urls on non-AWS cloud platforms.
Besides feature_overrides.py, users can override this by providing
#cloud-config apt directives.
"""

try:
    # pylint: disable=wildcard-import
    from cloudinit.feature_overrides import *  # noqa
except ImportError:
    pass
