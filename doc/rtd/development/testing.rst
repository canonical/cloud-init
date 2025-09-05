.. _testing:

Testing
*******

``Cloud-init`` has both unit tests and integration tests. Unit tests can
be found at :file:`tests/unittests`. Integration tests can be found at
:file:`tests/integration_tests`. Documentation specifically for integration
tests can be found on the :ref:`integration_tests` page, but
the guidelines specified below apply to both types of tests.

``Cloud-init`` uses `pytest`_ to write and run its tests.

.. note::
  While there are a subset of tests written as ``unittest.TestCase``
  sub-classes, this is due to historical reasons. Their use is discouraged and
  they are tracked to be removed in `#6427`_.

Guidelines
==========

The following guidelines should be followed.

Test layout
-----------

* For consistency, unit test files should have a matching name and
  directory location under :file:`tests/unittests`.

* E.g., the expected test file for code in :file:`cloudinit/path/to/file.py`
  is :file:`tests/unittests/path/to/test_file.py`.

``pytest`` guidelines
---------------------

* Use `pytest fixtures`_ to share functionality instead of inheritance.

* Use bare ``assert`` statements, to take advantage of ``pytest``'s
  `assertion introspection`_.

* Prefer ``pytest``'s
  `parametrized tests <https://docs.pytest.org/en/stable/example/parametrize.html>`__
  over test repetition.

In-house fixtures
-----------------

Before implementing your own fixture do search in :file:`*/conftest.py` files
as it could be already implemented. Another source to look for test helpers is
:file:`tests/*/helpers.py`.

Relevant fixtures:

* `disable_subp_usage`_ auto-disables call to subprocesses. See its
  documentation to disable it.

* `fake_filesystem`_ makes tests run on a temporary filesystem.

* `paths`_  provides an instance of `cloudinit.helper.Paths` pointing to a
  temporary filesystem.

Dependency versions
-------------------

Cloud-init supports a range of versions for each of its test dependencies, as
well as runtime dependencies. If you are unsure whether a specific feature is
supported for a particular dependency, check the ``lowest-supported``
environment in ``tox.ini``. This can be run using ``tox -e lowest-supported``.
This runs as a Github Actions job when a pull request is submitted or updated.

Mocking and assertions
----------------------

* Variables/parameter names for ``Mock`` or ``MagicMock`` instances
  should start with ``m_`` to clearly distinguish them from non-mock
  variables. For example, ``m_readurl`` (which would be a mock for
  ``readurl``).

* The ``assert_*`` methods that are available on ``Mock`` and
  ``MagicMock`` objects should be avoided, as typos in these method
  names may not raise ``AttributeError`` (and so can cause tests to
  silently pass).

  * **An important exception:** if a ``Mock`` is `autospecced`_ then
    misspelled assertion methods *will* raise an ``AttributeError``, so these
    assertion methods may be used on autospecced ``Mock`` objects.

* For a non-autospecced ``Mock``, these substitutions can be used
  (``m`` is assumed to be a ``Mock``):

  * ``m.assert_any_call(*args, **kwargs)`` => ``assert
    mock.call(*args, **kwargs) in m.call_args_list``
  * ``m.assert_called()`` => ``assert 0 != m.call_count``
  * ``m.assert_called_once()`` => ``assert 1 == m.call_count``
  * ``m.assert_called_once_with(*args, **kwargs)`` => ``assert
    [mock.call(*args, **kwargs)] == m.call_args_list``
  * ``m.assert_called_with(*args, **kwargs)`` => ``assert
    mock.call(*args, **kwargs) == m.call_args_list[-1]``
  * ``m.assert_has_calls(call_list, any_order=True)`` => ``for call in
    call_list: assert call in m.call_args_list``

    * ``m.assert_has_calls(...)`` and ``m.assert_has_calls(...,
      any_order=False)`` are not easily replicated in a single
      statement, so their use when appropriate is acceptable.

  * ``m.assert_not_called()`` => ``assert 0 == m.call_count``

* When there are multiple patch calls in a test file for the module it
  is testing, it may be desirable to capture the shared string prefix
  for these patch calls in a module-level variable. If used, such
  variables should be named ``M_PATH`` or, for datasource tests, ``DS_PATH``.

Test argument ordering
----------------------

* Test arguments should be ordered as follows:

  * ``mock.patch`` arguments.  When used as a decorator, ``mock.patch``
    partially applies its generated ``Mock`` object as the first
    argument, so these arguments must go first.
  * ``pytest.mark.parametrize`` arguments, in the order specified to
    the ``parametrize`` decorator. These arguments are also provided
    by a decorator, so it's natural that they sit next to the
    ``mock.patch`` arguments.
  * Fixture arguments, alphabetically. These are not provided by a
    decorator, so they are last, and their order has no defined
    meaning, so we default to alphabetical.

* It follows from this ordering of test arguments (so that we retain
  the property that arguments left-to-right correspond to decorators
  bottom-to-top) that test decorators should be ordered as follows:

  * ``pytest.mark.parametrize``
  * ``mock.patch``

.. LINKS:
.. _pytest: https://docs.pytest.org/
.. _pytest fixtures: https://docs.pytest.org/en/latest/fixture.html
.. _TestGetPackageMirrorInfo: https://github.com/canonical/cloud-init/blob/42f69f410ab8850c02b1f53dd67c132aa8ef64f5/cloudinit/distros/tests/test_init.py\#L15
.. _TestPrependBaseCommands: https://github.com/canonical/cloud-init/blob/fbcb224bc12495ba200ab107246349d802c5d8e6/cloudinit/tests/test_subp.py#L20
.. _assertion introspection: https://docs.pytest.org/en/latest/assert.html
.. _pytest 3.0: https://docs.pytest.org/en/latest/changelog.html#id1093
.. _pytest.param: https://docs.pytest.org/en/6.2.x/reference.html#pytest-param
.. _autospecced: https://docs.python.org/3.8/library/unittest.mock.html#autospeccing
.. _#6427: https://github.com/canonical/cloud-init/issues/6427
.. _disable_subp_usage: https://github.com/canonical/cloud-init/blob/16f2039d0705ee9873ace98c967a34e6da6d0b87/conftest.py#L92
.. _fake_filesystem: https://github.com/canonical/cloud-init/blob/16f2039d0705ee9873ace98c967a34e6da6d0b87/tests/unittests/conftest.py#L114
.. _paths: https://github.com/canonical/cloud-init/blob/16f2039d0705ee9873ace98c967a34e6da6d0b87/tests/unittests/conftest.py#L224
