# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloudinit.temp_utils"""

from cloudinit.temp_utils import mkdtemp, mkstemp
from cloudinit.tests.helpers import CiTestCase, wrap_and_call


class TestTempUtils(CiTestCase):

    def test_mkdtemp_default_non_root(self):
        """mkdtemp creates a dir under /tmp for the unprivileged."""
        calls = []

        def fake_mkdtemp(*args, **kwargs):
            calls.append(kwargs)
            return '/fake/return/path'

        retval = wrap_and_call(
            'cloudinit.temp_utils',
            {'os.getuid': 1000,
             'tempfile.mkdtemp': {'side_effect': fake_mkdtemp},
             '_TMPDIR': {'new': None},
             'os.path.isdir': True},
            mkdtemp)
        self.assertEqual('/fake/return/path', retval)
        self.assertEqual([{'dir': '/tmp'}], calls)

    def test_mkdtemp_default_non_root_needs_exe(self):
        """mkdtemp creates a dir under /var/tmp/cloud-init when needs_exe."""
        calls = []

        def fake_mkdtemp(*args, **kwargs):
            calls.append(kwargs)
            return '/fake/return/path'

        retval = wrap_and_call(
            'cloudinit.temp_utils',
            {'os.getuid': 1000,
             'tempfile.mkdtemp': {'side_effect': fake_mkdtemp},
             '_TMPDIR': {'new': None},
             'os.path.isdir': True},
            mkdtemp, needs_exe=True)
        self.assertEqual('/fake/return/path', retval)
        self.assertEqual([{'dir': '/var/tmp/cloud-init'}], calls)

    def test_mkdtemp_default_root(self):
        """mkdtemp creates a dir under /run/cloud-init for the privileged."""
        calls = []

        def fake_mkdtemp(*args, **kwargs):
            calls.append(kwargs)
            return '/fake/return/path'

        retval = wrap_and_call(
            'cloudinit.temp_utils',
            {'os.getuid': 0,
             'tempfile.mkdtemp': {'side_effect': fake_mkdtemp},
             '_TMPDIR': {'new': None},
             'os.path.isdir': True},
            mkdtemp)
        self.assertEqual('/fake/return/path', retval)
        self.assertEqual([{'dir': '/run/cloud-init/tmp'}], calls)

    def test_mkstemp_default_non_root(self):
        """mkstemp creates secure tempfile under /tmp for the unprivileged."""
        calls = []

        def fake_mkstemp(*args, **kwargs):
            calls.append(kwargs)
            return '/fake/return/path'

        retval = wrap_and_call(
            'cloudinit.temp_utils',
            {'os.getuid': 1000,
             'tempfile.mkstemp': {'side_effect': fake_mkstemp},
             '_TMPDIR': {'new': None},
             'os.path.isdir': True},
            mkstemp)
        self.assertEqual('/fake/return/path', retval)
        self.assertEqual([{'dir': '/tmp'}], calls)

    def test_mkstemp_default_root(self):
        """mkstemp creates a secure tempfile in /run/cloud-init for root."""
        calls = []

        def fake_mkstemp(*args, **kwargs):
            calls.append(kwargs)
            return '/fake/return/path'

        retval = wrap_and_call(
            'cloudinit.temp_utils',
            {'os.getuid': 0,
             'tempfile.mkstemp': {'side_effect': fake_mkstemp},
             '_TMPDIR': {'new': None},
             'os.path.isdir': True},
            mkstemp)
        self.assertEqual('/fake/return/path', retval)
        self.assertEqual([{'dir': '/run/cloud-init/tmp'}], calls)

# vi: ts=4 expandtab
