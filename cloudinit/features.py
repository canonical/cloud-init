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
decompress fails) and ``ERROR_ON_USER_DATA_FAILURE`` is ``False``,
cloud-init will log a warning and proceed.  If it is ``True``,
cloud-init will instead raise an exception.

As of 20.3, ``ERROR_ON_USER_DATA_FAILURE`` is ``True``.

(This flag can be removed after Focal is no longer supported.)
"""


ALLOW_EC2_MIRRORS_ON_NON_AWS_INSTANCE_TYPES = False
"""
When configuring apt mirrors, if
``ALLOW_EC2_MIRRORS_ON_NON_AWS_INSTANCE_TYPES`` is ``True`` cloud-init
will detect that a datasource's ``availability_zone`` property looks
like an EC2 availability zone and set the ``ec2_region`` variable when
generating mirror URLs; this can lead to incorrect mirrors being
configured in clouds whose AZs follow EC2's naming pattern.

As of 20.3, ``ALLOW_EC2_MIRRORS_ON_NON_AWS_INSTANCE_TYPES`` is ``False``
so we no longer include ``ec2_region`` in mirror determination on
non-AWS cloud platforms.

If the old behavior is desired, users can provide the appropriate
mirrors via :py:mod:`apt: <cloudinit.config.cc_apt_configure>`
directives in cloud-config.
"""

try:
    # pylint: disable=wildcard-import
    from cloudinit.feature_overrides import *  # noqa
except ImportError:
    pass
