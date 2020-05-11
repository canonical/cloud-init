*********************
Hacking on cloud-init
*********************

This document describes how to contribute changes to cloud-init.
It assumes you have a `GitHub`_ account, and refers to your GitHub user
as ``GH_USER`` throughout.

Submitting your first pull request
==================================

Follow these steps to submit your first pull request to cloud-init:

* To contribute to cloud-init, you must sign the Canonical `contributor
  license agreement`_

  * If you have already signed it as an individual, your Launchpad user
    will be listed in the `contributor-agreement-canonical`_ group.
    (Unfortunately there is no easy way to check if an organization or
    company you are doing work for has signed.)

  * When signing it:

    * ensure that you fill in the GitHub username field.
    * when prompted for 'Project contact' or 'Canonical Project
      Manager', enter 'Rick Harding'.

  * If your company has signed the CLA for you, please contact us to
    help in verifying which Launchpad/GitHub accounts are associated
    with the company.

  * For any questions or help with the process, please email `Rick
    Harding <mailto:rick.harding@canonical.com>`_ with the subject,
    "Cloud-Init CLA"

  * You also may contact user ``rick_h`` in the ``#cloud-init``
    channel on the Freenode IRC network.

* Configure git with your email and name for commit messages.

  Your name will appear in commit messages and will also be used in
  changelogs or release notes.  Give yourself credit!::

    git config user.name "Your Name"
    git config user.email "Your Email"

* Sign into your `GitHub`_ account

* Fork the upstream `repository`_ on Github and clicking on the ``Fork`` button

* Create a new remote pointing to your personal GitHub repository.

  .. code:: sh

    git clone git://github.com/canonical/cloud-init
    cd cloud-init
    git remote add GH_USER git@github.com:GH_USER/cloud-init.git
    git push GH_USER master

* Read through the cloud-init `Code Review Process`_, so you understand
  how your changes will end up in cloud-init's codebase.

* Submit your first cloud-init pull request, adding yourself to the
  in-repository list that we use to track CLA signatures:
  `tools/.github-cla-signers`_

  * See `PR #344`_ and `PR #345`_ for examples of what this pull
    request should look like.

  * (If you already have a change that you want to submit, you can
    also include the change to ``tools/.github-cla-signers`` in that
    pull request, there is no need for two separate PRs.)

.. _GitHub: https://github.com
.. _Launchpad: https://launchpad.net
.. _repository: https://github.com/canonical/cloud-init
.. _contributor license agreement: https://ubuntu.com/legal/contributors
.. _contributor-agreement-canonical: https://launchpad.net/%7Econtributor-agreement-canonical/+members
.. _tools/.github-cla-signers: https://github.com/canonical/cloud-init/blob/master/tools/.github-cla-signers
.. _PR #344: https://github.com/canonical/cloud-init/pull/344
.. _PR #345: https://github.com/canonical/cloud-init/pull/345

Transferring CLA Signatures from Launchpad to Github
----------------------------------------------------

For existing contributors who have signed the agreement in Launchpad
before the Github username field was included, we need to verify the
link between your `Launchpad`_ account and your `GitHub`_ account.  To
enable us to do this, we ask that you create a branch with both your
Launchpad and GitHub usernames against both the Launchpad and GitHub
cloud-init repositories.  We've added a tool
(``tools/migrate-lp-user-to-github``) to the cloud-init repository to
handle this migration as automatically as possible.

The cloud-init team will review the two merge proposals and verify that
the CLA has been signed for the Launchpad user and record the
associated GitHub account.

Do these things for each feature or bug
=======================================

* Create a new topic branch for your work::

    git checkout -b my-topic-branch

* Make and commit your changes (note, you can make multiple commits,
  fixes, more commits.)::

    git commit

* Run unit tests and lint/formatting checks with `tox`_::

    tox

* Push your changes to your personal GitHub repository::

    git push -u GH_USER my-topic-branch

* Use your browser to create a merge request:

  - Open the branch on GitHub

    - You can see a web view of your repository and navigate to the branch at:

      ``https://github.com/GH_USER/cloud-init/tree/my-topic-branch``

  - Click 'Pull Request`
  - Fill out the pull request title, summarizing the change and a longer
    message indicating important details about the changes included, like ::

      Activate the frobnicator.

      The frobnicator was previously inactive and now runs by default.
      This may save the world some day.  Then, list the bugs you fixed
      as footers with syntax as shown here.

      The commit message should be one summary line of less than
      74 characters followed by a blank line, and then one or more
      paragraphs describing the change and why it was needed.

      This is the message that will be used on the commit when it
      is sqaushed and merged into trunk.

      LP: #1

    Note that the project continues to use LP: #NNNNN format for closing
    launchpad bugs rather than GitHub Issues.

  - Click 'Create Pull Request`

Then, someone in the `Ubuntu Server`_ team will review your changes and
follow up in the pull request.  Look at the `Code Review Process`_ doc
to understand the following steps.

Feel free to ping and/or join ``#cloud-init`` on freenode irc if you
have any questions.

.. _tox: https://tox.readthedocs.io/en/latest/
.. _Ubuntu Server: https://github.com/orgs/canonical/teams/ubuntu-server
.. _Code Review Process: https://cloudinit.readthedocs.io/en/latest/topics/code_review.html

Design
======

This section captures design decisions that are helpful to know when
hacking on cloud-init.

Cloud Config Modules
--------------------

* Any new modules should use underscores in any new config options and not
  hyphens (e.g. `new_option` and *not* `new-option`).

Unit Testing
------------

cloud-init uses `pytest`_ to run its tests, and has tests written both
as ``unittest.TestCase`` sub-classes and as un-subclassed pytest tests.
The following guidelines should be followed:

* For ease of organisation and greater accessibility for developers not
  familiar with pytest, all cloud-init unit tests must be contained
  within test classes

  * Put another way, module-level test functions should not be used

* pytest test classes should use `pytest fixtures`_ to share
  functionality instead of inheritance

* As all tests are contained within classes, it is acceptable to mix
  ``TestCase`` test classes and pytest test classes within the same
  test file

  * These can be easily distinguished by their definition: pytest
    classes will not use inheritance at all (e.g.
    `TestGetPackageMirrorInfo`_), whereas ``TestCase`` classes will
    subclass (indirectly) from ``TestCase`` (e.g.
    `TestPrependBaseCommands`_)

* pytest tests should use bare ``assert`` statements, to take advantage
  of pytest's `assertion introspection`_

  * For ``==`` and other commutative assertions, the expected value
    should be placed before the value under test:
    ``assert expected_value == function_under_test()``

* As we still support Ubuntu 16.04 (Xenial Xerus), we can only use
  pytest features that are available in v2.8.7.  This is an
  inexhaustive list of ways in which this may catch you out:

  * Support for using ``yield`` in ``pytest.fixture`` functions was
    only introduced in `pytest 3.0`_.  Such functions must instead use
    the ``pytest.yield_fixture`` decorator.

  * Only the following built-in fixtures are available
    [#fixture-list]_:

    * ``cache``
    * ``capsys``
    * ``capfd``
    * ``record_xml_property``
    * ``monkeypatch``
    * ``pytestconfig``
    * ``recwarn``
    * ``tmpdir_factory``
    * ``tmpdir``

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

* When there are multiple patch calls in a test file for the module it
  is testing, it may be desirable to capture the shared string prefix
  for these patch calls in a module-level variable.  If used, such
  variables should be named ``M_PATH`` or, for datasource tests,
  ``DS_PATH``.

.. _pytest: https://docs.pytest.org/
.. _pytest fixtures: https://docs.pytest.org/en/latest/fixture.html
.. _TestGetPackageMirrorInfo: https://github.com/canonical/cloud-init/blob/42f69f410ab8850c02b1f53dd67c132aa8ef64f5/cloudinit/distros/tests/test_init.py\#L15
.. _TestPrependBaseCommands: https://github.com/canonical/cloud-init/blob/master/cloudinit/tests/test_subp.py#L9
.. _assertion introspection: https://docs.pytest.org/en/latest/assert.html
.. _pytest 3.0: https://docs.pytest.org/en/latest/changelog.html#id1093
.. _autospecced: https://docs.python.org/3.8/library/unittest.mock.html#autospeccing

Type Annotations
----------------

The cloud-init codebase uses Python's annotation support for storing
type annotations in the style specified by `PEP-484`_.  Their use in
the codebase is encouraged but with one important caveat: types from
the ``typing`` module cannot be used.

cloud-init still supports Python 3.4, which doesn't have the ``typing``
module in the stdlib.  This means that the use of any types from the
``typing`` module in the codebase would require installation of an
additional Python module on platforms using Python 3.4.  As such
platforms are generally in maintenance mode, the introduction of a new
dependency may act as a break in compatibility in practical terms.

Similarly, only function annotations are appropriate for use, as the
variable annotations specified in `PEP-526`_ were introduced in Python
3.6.

.. _PEP-484: https://www.python.org/dev/peps/pep-0484/
.. _PEP-526: https://www.python.org/dev/peps/pep-0526/

.. [#fixture-list] This list of fixtures (with markup) can be
   reproduced by running::

     py.test-3 --fixtures -q | grep "^[^ ]" | grep -v no | sed 's/.*/* ``\0``/'

   in a xenial lxd container with python3-pytest installed.
