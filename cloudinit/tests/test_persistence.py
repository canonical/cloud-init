# Copyright (C) 2020 Canonical Ltd.
#
# Author: Daniel Watkins <oddbloke@ubuntu.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""
Tests for cloudinit.persistence.

Per https://docs.python.org/3/library/pickle.html, only "classes that are
defined at the top level of a module" can be pickled.  This means that all of
our ``CloudInitPickleMixin`` subclasses for testing must be defined at
module-level (rather than being defined inline or dynamically in the body of
test methods, as we would do without this constraint).

``TestPickleMixin.test_subclasses`` iterates over a list of all of these
classes, and tests that they round-trip through a pickle dump/load.  As the
interface we're testing is that ``_unpickle`` is called appropriately on
subclasses, our subclasses define their assertions in their ``_unpickle``
implementation.  (This means that the assertions will not be executed if
``_unpickle`` is not called at all; we have
``TestPickleMixin.test_unpickle_called`` to ensure it is called.)

To avoid manually maintaining a list of classes for parametrization we use a
simple metaclass, ``_Collector``, to gather them up.
"""

import pickle
from unittest import mock

import pytest

from cloudinit.persistence import CloudInitPickleMixin


class _Collector(type):
    """Any class using this as a metaclass will be stored in test_classes."""

    test_classes = []

    def __new__(cls, *args):
        new_cls = super().__new__(cls, *args)
        _Collector.test_classes.append(new_cls)
        return new_cls


class InstanceVersionNotUsed(CloudInitPickleMixin, metaclass=_Collector):
    """Test that the class version is used over one set in instance state."""

    _ci_pkl_version = 1

    def __init__(self):
        self._ci_pkl_version = 2

    def _unpickle(self, ci_pkl_version: int) -> None:
        assert 1 == ci_pkl_version


class MissingVersionHandled(CloudInitPickleMixin, metaclass=_Collector):
    """Test that pickles without ``_ci_pkl_version`` are handled gracefully.

    This is tested by overriding ``__getstate__`` so the dumped pickle of this
    class will not have ``_ci_pkl_version`` included.
    """

    def __getstate__(self):
        return self.__dict__

    def _unpickle(self, ci_pkl_version: int) -> None:
        assert 0 == ci_pkl_version


class OverridenVersionHonored(CloudInitPickleMixin, metaclass=_Collector):
    """Test that the subclass's version is used."""

    _ci_pkl_version = 1

    def _unpickle(self, ci_pkl_version: int) -> None:
        assert 1 == ci_pkl_version


class StateIsRestored(CloudInitPickleMixin, metaclass=_Collector):
    """Instance state should be restored before ``_unpickle`` is called."""

    def __init__(self):
        self.some_state = "some state"

    def _unpickle(self, ci_pkl_version: int) -> None:
        assert "some state" == self.some_state


class UnpickleCanBeUnoverriden(CloudInitPickleMixin, metaclass=_Collector):
    """Subclasses should not need to override ``_unpickle``."""


class VersionDefaultsToZero(CloudInitPickleMixin, metaclass=_Collector):
    """Test that the default version is 0."""

    def _unpickle(self, ci_pkl_version: int) -> None:
        assert 0 == ci_pkl_version


class VersionIsPoppedFromState(CloudInitPickleMixin, metaclass=_Collector):
    """Test _ci_pkl_version is popped from state before being restored."""

    def _unpickle(self, ci_pkl_version: int) -> None:
        # `self._ci_pkl_version` returns the type's _ci_pkl_version if it isn't
        # in instance state, so we need to explicitly check self.__dict__.
        assert "_ci_pkl_version" not in self.__dict__


class TestPickleMixin:
    def test_unpickle_called(self):
        """Test that self._unpickle is called on unpickle."""
        with mock.patch.object(
            CloudInitPickleMixin, "_unpickle"
        ) as m_unpickle:
            pickle.loads(pickle.dumps(CloudInitPickleMixin()))
        assert 1 == m_unpickle.call_count

    @pytest.mark.parametrize("cls", _Collector.test_classes)
    def test_subclasses(self, cls):
        """For each collected class, round-trip through pickle dump/load.

        Assertions are implemented in ``cls._unpickle``, and so are evoked as
        part of the pickle load.
        """
        pickle.loads(pickle.dumps(cls()))
