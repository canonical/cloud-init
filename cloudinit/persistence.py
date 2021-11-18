# Copyright (C) 2020 Canonical Ltd.
#
# Author: Daniel Watkins <oddbloke@ubuntu.com>
#
# This file is part of cloud-init. See LICENSE file for license information.


class CloudInitPickleMixin:
    """Scaffolding for versioning of pickles.

    This class implements ``__getstate__`` and ``__setstate__`` to provide
    lightweight versioning of the pickles that are generated for classes which
    use it.  Versioning is done at the class level.

    The current version of a class's pickle should be set in the class variable
    ``_ci_pkl_version``, as an int.  If not overriden, it will default to 0.

    On unpickle, the object's state will be restored and then
    ``self._unpickle`` is called with the version of the stored pickle as the
    only argument: this is where classes should implement any deserialization
    fixes they require.  (If the stored pickle has no version, 0 is passed.)
    """

    _ci_pkl_version = 0

    def __getstate__(self):
        """Persist instance state, adding a pickle version attribute.

        This adds a ``_ci_pkl_version`` attribute to ``self.__dict__`` and
        returns that for serialisation.  The attribute is stripped out in
        ``__setstate__`` on unpickle.

        The value of ``_ci_pkl_version`` is ``type(self)._ci_pkl_version``.
        """
        state = self.__dict__.copy()
        state["_ci_pkl_version"] = type(self)._ci_pkl_version
        return state

    def __setstate__(self, state: dict) -> None:
        """Restore instance state and handle missing attributes on upgrade.

        This will be called when an instance of this class is unpickled; the
        previous instance's ``__dict__`` is passed as ``state``.  This method
        removes the pickle version from the stored state, restores the
        remaining state into the current instance, and then calls
        ``self._unpickle`` with the version (or 0, if no version is found in
        the stored state).

        See https://docs.python.org/3/library/pickle.html#object.__setstate__
        for further background.
        """
        version = state.pop("_ci_pkl_version", 0)
        self.__dict__.update(state)
        self._unpickle(version)

    def _unpickle(self, ci_pkl_version: int) -> None:
        """Perform any deserialization fixes required.

        By default, this does nothing.  Classes using this mixin should
        override this method if they have fixes they need to apply.

        ``ci_pkl_version`` will be the version stored in the pickle for this
        object, or 0 if no version is present.
        """


# vi: ts=4 expandtab
