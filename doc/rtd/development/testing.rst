.. _testing:

Testing
*******

``Cloud-init`` has both unit tests and integration tests. Unit tests can
be found at :file:`tests/unittests`. Integration tests can be found at
:file:`tests/integration_tests`. Documentation specifically for integration
tests can be found on the :ref:`integration_tests` page, but
the guidelines specified below apply to both types of tests.

``Cloud-init`` uses `pytest`_ to run its tests, and has tests written both
as ``unittest.TestCase`` sub-classes and as un-subclassed ``pytest`` tests.

Guidelines
==========

The following guidelines should be followed.

Test layout
-----------

* For ease of organisation and greater accessibility for developers unfamiliar
  with ``pytest``, all ``cloud-init`` unit tests must be contained within test
  classes. In other words, module-level test functions should not be used.

* Since all tests are contained within classes, it is acceptable to mix
  ``TestCase`` test classes and ``pytest`` test classes within the same
  test file.

  * These can be easily distinguished by their definition: ``pytest``
    classes will not use inheritance at all (e.g.,
    `TestGetPackageMirrorInfo`_), whereas ``TestCase`` classes will
    subclass (indirectly) from ``TestCase`` (e.g.,
    `TestPrependBaseCommands`_).

* Unit tests and integration tests are located under :file:`cloud-init/tests`.

  * For consistency, unit test files should have a matching name and
    directory location under :file:`tests/unittests`.

  * E.g., the expected test file for code in :file:`cloudinit/path/to/file.py`
    is :file:`tests/unittests/path/to/test_file.py`.

``pytest`` tests
----------------

* ``pytest`` test classes should use `pytest fixtures`_ to share
  functionality instead of inheritance.

* ``pytest`` tests should use bare ``assert`` statements, to take advantage
  of ``pytest``'s `assertion introspection`_.

``pytest`` version "gotchas"
----------------------------

As we still support Ubuntu 18.04 (Bionic Beaver), we can only use ``pytest``
features that are available in v3.3.2. This is an inexhaustive list of
ways in which this may catch you out:

  * Only the following built-in fixtures are available [#fixture-list]_:

    * ``cache``
    * ``capfd``
    * ``capfdbinary``
    * ``caplog``
    * ``capsys``
    * ``capsysbinary``
    * ``doctest_namespace``
    * ``monkeypatch``
    * ``pytestconfig``
    * ``record_xml_property``
    * ``recwarn``
    * ``tmpdir_factory``
    * ``tmpdir``

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

.. [#fixture-list] This list of fixtures (with markup) can be
   reproduced by running::

     python3 -m pytest  --fixtures -q | grep "^[^ -]" | grep -v 'no tests ran in' | sort | sed 's/ \[session scope\]//g;s/.*/* ``\0``/g'

   in an ubuntu lxd container with python3-pytest installed.

.. LINKS:
.. _pytest: https://docs.pytest.org/
.. _pytest fixtures: https://docs.pytest.org/en/latest/fixture.html
.. _TestGetPackageMirrorInfo: https://github.com/canonical/cloud-init/blob/42f69f410ab8850c02b1f53dd67c132aa8ef64f5/cloudinit/distros/tests/test_init.py\#L15
.. _TestPrependBaseCommands: https://github.com/canonical/cloud-init/blob/fbcb224bc12495ba200ab107246349d802c5d8e6/cloudinit/tests/test_subp.py#L20
.. _assertion introspection: https://docs.pytest.org/en/latest/assert.html
.. _pytest 3.0: https://docs.pytest.org/en/latest/changelog.html#id1093
.. _pytest.param: https://docs.pytest.org/en/6.2.x/reference.html#pytest-param
.. _autospecced: https://docs.python.org/3.8/library/unittest.mock.html#autospeccing
