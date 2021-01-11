*******
Testing
*******

cloud-init has both unit tests and integration tests. Unit tests can
be found in-tree alongside the source code, as well as
at ``tests/unittests``. Integration tests can be found at
``tests/integration_tests``. Documentation specifically for integration
tests can be found on the :ref:`integration_tests` page, but
the guidelines specified below apply to both types of tests.

cloud-init uses `pytest`_ to run its tests, and has tests written both
as ``unittest.TestCase`` sub-classes and as un-subclassed pytest tests.

Guidelines
==========

The following guidelines should be followed.

Test Layout
-----------

* For ease of organisation and greater accessibility for developers not
  familiar with pytest, all cloud-init unit tests must be contained
  within test classes

  * Put another way, module-level test functions should not be used

* As all tests are contained within classes, it is acceptable to mix
  ``TestCase`` test classes and pytest test classes within the same
  test file

  * These can be easily distinguished by their definition: pytest
    classes will not use inheritance at all (e.g.
    `TestGetPackageMirrorInfo`_), whereas ``TestCase`` classes will
    subclass (indirectly) from ``TestCase`` (e.g.
    `TestPrependBaseCommands`_)

``pytest`` Tests
----------------

* pytest test classes should use `pytest fixtures`_ to share
  functionality instead of inheritance

* pytest tests should use bare ``assert`` statements, to take advantage
  of pytest's `assertion introspection`_

  * For ``==`` and other commutative assertions, the expected value
    should be placed before the value under test:
    ``assert expected_value == function_under_test()``


``pytest`` Version Gotchas
--------------------------

As we still support Ubuntu 16.04 (Xenial Xerus), we can only use pytest
features that are available in v2.8.7.  This is an inexhaustive list of
ways in which this may catch you out:

* Support for using ``yield`` in ``pytest.fixture`` functions was only
  introduced in `pytest 3.0`_.  Such functions must instead use the
  ``pytest.yield_fixture`` decorator.

* Only the following built-in fixtures are available [#fixture-list]_:

  * ``cache``
  * ``capfd``
  * ``caplog`` (provided by ``python3-pytest-catchlog`` on xenial)
  * ``capsys``
  * ``monkeypatch``
  * ``pytestconfig``
  * ``record_xml_property``
  * ``recwarn``
  * ``tmpdir_factory``
  * ``tmpdir``

* On xenial, the objects returned by the ``tmpdir`` fixture cannot be
  used where paths are required; they are rejected as invalid paths.
  You must instead use their ``.strpath`` attribute.

  * For example, instead of ``util.write_file(tmpdir.join("some_file"),
    ...)``, you should write
    ``util.write_file(tmpdir.join("some_file").strpath, ...)``.

* The `pytest.param`_ function cannot be used. It was introduced in
  pytest 3.1, which means it is not available on xenial.  The more
  limited mechanism it replaced was removed in pytest 4.0, so is not
  available in focal or later.  The only available alternatives are to
  write mark-requiring test instances as completely separate tests,
  without utilising parameterisation, or to apply the mark to the
  entire parameterized test (and therefore every test instance).

Mocking and Assertions
----------------------

* Variables/parameter names for ``Mock`` or ``MagicMock`` instances
  should start with ``m_`` to clearly distinguish them from non-mock
  variables

  * For example, ``m_readurl`` (which would be a mock for ``readurl``)

* The ``assert_*`` methods that are available on ``Mock`` and
  ``MagicMock`` objects should be avoided, as typos in these method
  names may not raise ``AttributeError`` (and so can cause tests to
  silently pass).  An important exception: if a ``Mock`` is
  `autospecced`_ then misspelled assertion methods *will* raise an
  ``AttributeError``, so these assertion methods may be used on
  autospecced ``Mock`` objects.

  For non-autospecced ``Mock`` s, these substitutions can be used
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
  for these patch calls in a module-level variable.  If used, such
  variables should be named ``M_PATH`` or, for datasource tests,
  ``DS_PATH``.

Test Argument Ordering
----------------------

* Test arguments should be ordered as follows:

  * ``mock.patch`` arguments.  When used as a decorator, ``mock.patch``
    partially applies its generated ``Mock`` object as the first
    argument, so these arguments must go first.
  * ``pytest.mark.parametrize`` arguments, in the order specified to
    the ``parametrize`` decorator.  These arguments are also provided
    by a decorator, so it's natural that they sit next to the
    ``mock.patch`` arguments.
  * Fixture arguments, alphabetically.  These are not provided by a
    decorator, so they are last, and their order has no defined
    meaning, so we default to alphabetical.

* It follows from this ordering of test arguments (so that we retain
  the property that arguments left-to-right correspond to decorators
  bottom-to-top) that test decorators should be ordered as follows:

  * ``pytest.mark.parametrize``
  * ``mock.patch``

.. [#fixture-list] This list of fixtures (with markup) can be
   reproduced by running::

     py.test-3 --fixtures -q | grep "^[^ -]" | grep -v '\(no\|capturelog\)' | sort | sed 's/.*/* ``\0``/'

   in a xenial lxd container with python3-pytest-catchlog installed.

.. _pytest: https://docs.pytest.org/
.. _pytest fixtures: https://docs.pytest.org/en/latest/fixture.html
.. _TestGetPackageMirrorInfo: https://github.com/canonical/cloud-init/blob/42f69f410ab8850c02b1f53dd67c132aa8ef64f5/cloudinit/distros/tests/test_init.py\#L15
.. _TestPrependBaseCommands: https://github.com/canonical/cloud-init/blob/master/cloudinit/tests/test_subp.py#L9
.. _assertion introspection: https://docs.pytest.org/en/latest/assert.html
.. _pytest 3.0: https://docs.pytest.org/en/latest/changelog.html#id1093
.. _pytest.param: https://docs.pytest.org/en/latest/reference.html#pytest-param
.. _autospecced: https://docs.python.org/3.8/library/unittest.mock.html#autospeccing
