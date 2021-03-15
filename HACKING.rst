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

  * Note that ``.github-cla-signers`` is sorted alphabetically.

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

.. note::
   If you are a first time contributor, you will not need to touch
   Launchpad to contribute to cloud-init: all new CLA signatures are
   handled as part of the GitHub pull request process described above.

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

Tests
-----

Submissions to cloud-init must include testing.  See :ref:`testing` for
details on these requirements.

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

Feature Flags
-------------

.. automodule:: cloudinit.features
   :members:


Ongoing Refactors
=================

This captures ongoing refactoring projects in the codebase.  This is
intended as documentation for developers involved in the refactoring,
but also for other developers who may interact with the code being
refactored in the meantime.

``cloudinit.net`` -> ``cloudinit.distros.networking`` Hierarchy
---------------------------------------------------------------

``cloudinit.net`` was imported from the curtin codebase as a chunk, and
then modified enough that it integrated with the rest of the cloud-init
codebase.  Over the ~4 years since, the fact that it is not fully
integrated into the ``Distro`` hierarchy has caused several issues.

The common pattern of these problems is that the commands used for
networking are different across distributions and operating systems.
This has lead to ``cloudinit.net`` developing its own "distro
determination" logic: `get_interfaces_by_mac`_ is probably the clearest
example of this.  Currently, these differences are primarily split
along Linux/BSD lines.  However, it would be short-sighted to only
refactor in a way that captures this difference: we can anticipate that
differences will develop between Linux-based distros in future, or
there may already be differences in tooling that we currently
work around in less obvious ways.

The high-level plan is to introduce a hierarchy of networking classes
in ``cloudinit.distros.networking``, which each ``Distro`` subclass
will reference.  These will capture the differences between networking
on our various distros, while still allowing easy reuse of code between
distros that share functionality (e.g. most of the Linux networking
behaviour).  ``Distro`` objects will instantiate the networking classes
at ``self.networking``, so callers will call
``distro.networking.<func>`` instead of ``cloudinit.net.<func>``; this
will necessitate access to an instantiated ``Distro`` object.

An implementation note: there may be external consumers of the
``cloudinit.net`` module.  We don't consider this a public API, so we
will be removing it as part of this refactor.  However, we will ensure
that the new API is complete from its introduction, so that any such
consumers can move over to it wholesale.  (Note, however, that this new
API is still not considered public or stable, and may not replicate the
existing API exactly.)

In more detail:

* The root of this hierarchy will be the
  ``cloudinit.distros.networking.Networking`` class.  This class will
  have a corresponding method for every ``cloudinit.net`` function that
  we identify to be involved in refactoring.  Initially, these methods'
  implementations will simply call the corresponding ``cloudinit.net``
  function.  (This gives us the complete API from day one, for existing
  consumers.)
* As the biggest differentiator in behaviour, the next layer of the
  hierarchy will be two subclasses: ``LinuxNetworking`` and
  ``BSDNetworking``.  These will be introduced in the initial PR.
* When a difference in behaviour for a particular distro is identified,
  a new ``Networking`` subclass will be created.  This new class should
  generally subclass either ``LinuxNetworking`` or ``BSDNetworking``.
* To be clear: ``Networking`` subclasses will only be created when
  needed, we will not create a full hierarchy of per-``Distro``
  subclasses up-front.
* Each ``Distro`` class will have a class variable
  (``cls.networking_cls``) which points at the appropriate
  networking class (initially this will be either ``LinuxNetworking``
  or ``BSDNetworking``).
* When ``Distro`` classes are instantiated, they will instantiate
  ``cls.networking_cls`` and store the instance at ``self.networking``.
  (This will be implemented in ``cloudinit.distros.Distro.__init__``.)
* A helper function will be added which will determine the appropriate
  ``Distro`` subclass for the current system, instantiate it and return
  its ``networking`` attribute.  (This is the entry point for existing
  consumers to migrate to.)
* Callers of refactored functions will change from calling
  ``cloudinit.net.<func>`` to ``distro.networking.<func>``, where
  ``distro`` is an instance of the appropriate ``Distro`` class for
  this system.  (This will require making such an instance available to
  callers, which will constitute a large part of the work in this
  project.)

After the initial structure is in place, the work in this refactor will
consist of replacing the ``cloudinit.net.some_func`` call in each
``cloudinit.distros.networking.Networking`` method with the actual
implementation.  This can be done incrementally, one function at a
time:

* pick an unmigrated ``cloudinit.distros.networking.Networking`` method
* find it in the `the list of bugs tagged net-refactor`_ and assign
  yourself to it (see :ref:`Managing Work/Tracking Progress` below for
  more details)
* refactor all of its callers to call the ``distro.networking.<func>``
  method on ``Distro`` instead of the ``cloudinit.net.<func>``
  function. (This is likely to be the most time-consuming step, as it
  may require plumbing ``Distro`` objects through to places that
  previously have not consumed them.)
* refactor its implementation from ``cloudinit.net`` into the
  ``Networking`` hierarchy (e.g. if it has an if/else on BSD, this is
  the time to put the implementations in their respective subclasses)

  * if part of the method contains distro-independent logic, then you
    may need to create new methods to capture this distro-specific
    logic; we don't want to replicate common logic in different
    ``Networking`` subclasses
  * if after the refactor, the method on the root ``Networking`` class
    no longer has any implementation, it should be converted to an
    `abstractmethod`_

* ensure that the new implementation has unit tests (either by moving
  existing tests, or by writing new ones)
* ensure that the new implementation has a docstring
* add any appropriate type annotations

  * note that we must follow the constraints described in the "Type
    Annotations" section above, so you may not be able to write
    complete annotations
  * we have `type aliases`_ defined in ``cloudinit.distros.networking``
    which should be used when applicable

* finally, remove it (and any other now-unused functions) from
  cloudinit.net (to avoid having two parallel implementations)

``cloudinit.net`` Functions/Classes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The functions/classes that need refactoring break down into some broad
categories:

* helpers for accessing ``/sys`` (that should not be on the top-level
  ``Networking`` class as they are Linux-specific):

  * ``get_sys_class_path``
  * ``sys_dev_path``
  * ``read_sys_net``
  * ``read_sys_net_safe``
  * ``read_sys_net_int``

* those that directly access ``/sys`` (via helpers) and should (IMO) be
  included in the API of the ``Networking`` class:

  * ``generate_fallback_config``

    * the ``config_driver`` parameter is used and passed as a boolean,
      so we can change the default value to ``False`` (instead of
      ``None``)

  * ``get_ib_interface_hwaddr``
  * ``get_interface_mac``
  * ``interface_has_own_mac``
  * ``is_bond``
  * ``is_bridge``
  * ``is_physical``
  * ``is_renamed``
  * ``is_up``
  * ``is_vlan``
  * ``wait_for_physdevs``

* those that directly access ``/sys`` (via helpers) but may be
  Linux-specific concepts or names:

  * ``get_master``
  * ``device_devid``
  * ``device_driver``

* those that directly use ``ip``:

  * ``_get_current_rename_info``

    * this has non-distro-specific logic so should potentially be
      refactored to use helpers on ``self`` instead of ``ip`` directly
      (rather than being wholesale reimplemented in each of
      ``BSDNetworking`` or ``LinuxNetworking``)
    * we can also remove the ``check_downable`` argument, it's never
      specified so is always ``True``

  * ``_rename_interfaces``

    * this has several internal helper functions which use ``ip``
      directly, and it calls ``_get_current_rename_info``.  That said,
      there appears to be a lot of non-distro-specific logic that could
      live in a function on ``Networking``, so this will require some
      careful refactoring to avoid duplicating that logic in each of
      ``BSDNetworking`` and ``LinuxNetworking``.
    * only the ``renames`` and ``current_info`` parameters are ever
      passed in (and ``current_info`` only by tests), so we can remove
      the others from the definition

  * ``EphemeralIPv4Network``

    * this is another case where it mixes distro-specific and
      non-specific functionality.  Specifically, ``__init__``,
      ``__enter__`` and ``__exit__`` are non-specific, and the
      remaining methods are distro-specific.
    * when refactoring this, the need to track ``cleanup_cmds`` likely
      means that the distro-specific behaviour cannot be captured only
      in the ``Networking`` class.  See `this comment in PR #363`_ for
      more thoughts.

* those that implicitly use ``/sys`` via their call dependencies:

  * ``master_is_bridge_or_bond``

    * appends to ``get_master`` return value, which is a ``/sys`` path

  * ``extract_physdevs``

    * calls ``device_driver`` and ``device_devid`` in both
      ``_version_*`` impls

  * ``apply_network_config_names``

    * calls ``extract_physdevs``
    * there is already a ``Distro.apply_network_config_names`` which in
      the default implementation calls this function; this and its BSD
      subclass implementations should be refactored at the same time
    * the ``strict_present`` and ``strict_busy`` parameters are never
      passed, nor are they used in the function definition, so they can
      be removed

  * ``get_interfaces``

    * calls ``device_driver``, ``device_devid`` amongst others

  * ``get_ib_hwaddrs_by_interface``

    * calls ``get_interfaces``

* those that may fall into the above categories, but whose use is only
  related to netfailover (which relies on a Linux-specific network
  driver, so is unlikely to be relevant elsewhere without a substantial
  refactor; these probably only need implementing in
  ``LinuxNetworking``):

  * ``get_dev_features``

  * ``has_netfail_standby_feature``

    * calls ``get_dev_features``

  * ``is_netfailover``
  * ``is_netfail_master``

    * this is called from ``generate_fallback_config``

  * ``is_netfail_primary``
  * ``is_netfail_standby``

  * N.B. all of these take an optional ``driver`` argument which is
    used to pass around a value to avoid having to look it up by
    calling ``device_driver`` every time.  This is something of a leaky
    abstraction, and is better served by caching on ``device_driver``
    or storing the cached value on ``self``, so we can drop the
    parameter from the new API.

* those that use ``/sys`` (via helpers) and have non-exhaustive BSD
  logic:

  * ``get_devicelist``

* those that already have separate Linux/BSD implementations:

  * ``find_fallback_nic``
  * ``get_interfaces_by_mac``

* those that have no OS-specific functionality (so do not need to be
  refactored):

  * ``ParserError``
  * ``RendererNotFoundError``
  * ``has_url_connectivity``
  * ``is_ip_address``
  * ``is_ipv4_address``
  * ``natural_sort_key``

Note that the functions in ``cloudinit.net`` use inconsistent parameter
names for "string that contains a device name"; we can standardise on
``devname`` (the most common one) in the refactor.

Managing Work/Tracking Progress
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To ensure that we won't have multiple people working on the same part
of the refactor at the same time, there is a bug for each function.
You can see the current status by looking at `the list of bugs tagged
net-refactor`_.

When you're working on refactoring a particular method, ensure that you
have assigned yourself to the corresponding bug, to avoid duplicate
work.

Generally, when considering what to pick up to refactor, it is best to
start with functions in ``cloudinit.net`` which are not called by
anything else in ``cloudinit.net``.  This allows you to focus only on
refactoring that function and its callsites, rather than having to
update the other ``cloudinit.net`` function also.

References
~~~~~~~~~~

* `Mina Galić's email the the cloud-init ML in 2018`_ (plus its thread)
* `Mina Galić's email to the cloud-init ML in 2019`_ (plus its thread)
* `PR #363`_, the discussion which prompted finally starting this
  refactor (and where a lot of the above details were hashed out)

.. _get_interfaces_by_mac: https://github.com/canonical/cloud-init/blob/961239749106daead88da483e7319e9268c67cde/cloudinit/net/__init__.py#L810-L818
.. _Mina Galić's email the the cloud-init ML in 2018: https://lists.launchpad.net/cloud-init/msg00185.html
.. _Mina Galić's email to the cloud-init ML in 2019: https://lists.launchpad.net/cloud-init/msg00237.html
.. _PR #363: https://github.com/canonical/cloud-init/pull/363
.. _this comment in PR #363: https://github.com/canonical/cloud-init/pull/363#issuecomment-628829489
.. _abstractmethod: https://docs.python.org/3/library/abc.html#abc.abstractmethod
.. _type aliases: https://docs.python.org/3/library/typing.html#type-aliases
.. _the list of bugs tagged net-refactor: https://bugs.launchpad.net/cloud-init/+bugs?field.tag=net-refactor
