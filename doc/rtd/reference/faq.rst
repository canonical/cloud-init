.. _faq:

FAQ
***

How do I get help?
==================

Having trouble? We would like to help!

- First go through this page with answers to common questions
- Use the search bar at the upper left to search our documentation
- Ask questions in the ``#cloud-init`` `IRC channel on Libera`_
- Join and ask questions on the ``cloud-init`` `mailing list`_
- Find a bug? Check out the :ref:`reporting_bugs` topic to find out how to
  report one

Where are the logs?
===================

``Cloud-init`` uses two files to log to:

- :file:`/var/log/cloud-init-output.log`: Captures the output from each stage
  of ``cloud-init`` when it runs.
- :file:`/var/log/cloud-init.log`: Very detailed log with debugging output,
  detailing each action taken.
- :file:`/run/cloud-init`: contains logs about how ``cloud-init`` decided to
  enable or disable itself, as well as what platforms/datasources were
  detected. These logs are most useful when trying to determine what
  ``cloud-init`` did or did not run.

Be aware that each time a system boots, new logs are appended to the files in
:file:`/var/log`. Therefore, the files may have information present from more
than one boot.

When reviewing these logs look for any errors or Python tracebacks to check
for any errors.

Where are the configuration files?
==================================

``Cloud-init`` config is provided in two places:

- :file:`/etc/cloud/cloud.cfg`
- :file:`/etc/cloud/cloud.cfg.d/*.cfg`

These files can define the modules that run during instance initialisation,
the datasources to evaluate on boot, as well as other settings.

See the :ref:`configuration sources explanation<configuration>` and
:ref:`configuration reference<base_config_reference>` pages for more details.

Where are the data files?
=========================

Inside the :file:`/var/lib/cloud/` directory there are two important
subdirectories:

:file:`instance`
----------------

The :file:`/var/lib/cloud/instance` directory is a symbolic link that points
to the most recently used :file:`instance-id` directory. This folder contains
the information ``cloud-init`` received from datasources, including vendor and
user data. This can be helpful to review to ensure the correct data was passed.

It also contains the :file:`datasource` file that contains the full information
about which datasource was identified and used to set up the system.

Finally, the :file:`boot-finished` file is the last thing that
``cloud-init`` does.

:file:`data`
------------

The :file:`/var/lib/cloud/data` directory contain information related to the
previous boot:

* :file:`instance-id`: ID of the instance as discovered by ``cloud-init``.
  Changing this file has no effect.
* :file:`result.json`: JSON file that will show both the datasource used to
  set up the instance, and whether any errors occurred.
* :file:`status.json`: JSON file showing the datasource used, a breakdown of
  all four modules, whether any errors occurred, and the start and stop times.

What datasource am I using?
===========================

To correctly set up an instance, ``cloud-init`` must correctly identify the
cloud that it is on. Therefore, knowing which datasource is used on an
instance launch can aid in debugging.

To find out which datasource is being used run the :command:`cloud-id` command:

.. code-block:: shell-session

    $ cloud-id

This will tell you which datasource is being used, for example:

.. code-block::

    nocloud

If the ``cloud-id`` is not what is expected, then running the
:file:`ds-identify` script in debug mode and providing that in a bug can aid
in resolving any issues:

.. code-block:: shell-session

    $ sudo DEBUG_LEVEL=2 DI_LOG=stderr /usr/lib/cloud-init/ds-identify --force

The ``force`` parameter allows the command to be run again since the instance
has already launched. The other options increase the verbosity of logging and
put the logs to :file:`STDERR`.

How can I re-run datasource detection and ``cloud-init``?
=========================================================

If a user is developing a new datasource or working on debugging an issue it
may be useful to re-run datasource detection and the initial setup of
``cloud-init``.

To do this, force :file:`ds-identify` to re-run, clean up any logs, and
re-run ``cloud-init``:

.. code-block:: shell-session

   $ sudo DI_LOG=stderr /usr/lib/cloud-init/ds-identify --force
   $ sudo cloud-init clean --logs
   $ sudo cloud-init init --local
   $ sudo cloud-init init

.. warning::

    These commands will re-run ``cloud-init`` as if this were first boot of a
    system: this will, at the very least, cycle SSH host keys and may do
    substantially more. **Do not run these commands on production systems.**

How can I debug my user data?
=============================

Two of the most common issues with cloud config user data are:

1. Incorrectly formatted YAML
2. First line does not contain ``#cloud-config``

Static user data validation
---------------------------

To verify your cloud config is valid YAML you may use `validate-yaml.py`_.

To ensure that the keys and values in your user data are correct, you may run:

.. code-block:: shell-session

    $ cloud-init schema --system --annotate

or to test YAML in a file:

.. code-block:: shell-session

    $ cloud-init schema -c test.yml --annotate

Log analysis
------------

If you can log into your system, the best way to debug your system is to
check the contents of the log files :file:`/var/log/cloud-init.log` and
:file:`/var/log/cloud-init-output.log` for warnings, errors, and
tracebacks. Tracebacks are always reportable bugs.


Why did ``cloud-init`` never complete?
======================================

To check if ``cloud-init`` is running still, run:

.. code-block:: shell-session

        $ cloud-init status

To wait for ``cloud-init`` to complete, run:

.. code-block:: shell-session

        $ cloud-init status --wait

There are a number of reasons that ``cloud-init`` might never complete. This
list is not exhaustive, but attempts to enumerate potential causes:

External reasons
----------------

- Failed dependent services in the boot.
- Bugs in the kernel or drivers.
- Bugs in external userspace tools that are called by ``cloud-init``.

Internal reasons
----------------

- A command in ``bootcmd`` or ``runcmd`` that never completes (e.g., running
  :command:`cloud-init status --wait` will wait forever on itself and never
  complete).
- Non-standard configurations that disable timeouts or set extremely high
  values ("never" is used in a loose sense here).

Failing to complete on ``systemd``
----------------------------------

``Cloud-init`` consists of multiple services on ``systemd``. If a service
that ``cloud-init`` depends on stalls, ``cloud-init`` will not continue.
If reporting a bug related to ``cloud-init`` failing to complete on
``systemd``, please make sure to include the following logs.

.. code-block:: shell-session

        $ systemd-analyze critical-chain cloud-init.target
        $ journalctl --boot=-1
        $ systemctl --failed

``autoinstall``, ``preruncmd``, ``postruncmd``
==============================================

Since ``cloud-init`` ignores top level user data ``cloud-config`` keys, other
projects such as `Juju`_ and `Subiquity autoinstaller`_ use a YAML-formatted
config that combines ``cloud-init``'s user data cloud-config YAML format with
their custom YAML keys. Since ``cloud-init`` ignores unused top level keys,
these combined YAML configurations may be valid ``cloud-config`` files,
however keys such as ``autoinstall``, ``preruncmd``, and ``postruncmd`` are
not used by ``cloud-init`` to configure anything.

Please direct bugs and questions about other projects that use ``cloud-init``
to their respective support channels. For Subiquity autoinstaller that is via
IRC (``#ubuntu-server`` on Libera) or Discourse. For Juju support see their
`discourse page`_.


Can I use cloud-init as a library?
==================================
Yes, in fact some projects `already do`_. However, ``cloud-init`` does not
currently make any API guarantees to external consumers - current library
users are projects that have close contact with ``cloud-init``, which is why
this model currently works.

It is worth mentioning for library users that ``cloud-init`` defines a custom
log level. This log level, ``25``, is dedicated to logging info
related to deprecation information. Users of ``cloud-init`` as a library
may wish to ensure that this log level doesn't collide with external
libraries that define their own custom log levels.

Where can I learn more?
=======================

Below are some videos, blog posts, and white papers about ``cloud-init`` from a
variety of sources.

Videos:

- `cloud-init - The Good Parts`_
- `Perfect Proxmox Template with Cloud Image and Cloud Init`_
  [proxmox, cloud-init, template]
- `cloud-init - Building clouds one Linux box at a time (Video)`_
- `Metadata and cloud-init`_
- `Introduction to cloud-init`_

Blog Posts:

- `cloud-init - The cross-cloud Magic Sauce (PDF)`_
- `cloud-init - Building clouds one Linux box at a time (PDF)`_
- `The beauty of cloud-init`_
- `Cloud-init Getting Started`_ [fedora, libvirt, cloud-init]
- `Build Azure Devops Agents With Linux cloud-init for Dotnet Development`_
  [terraform, azure, devops, docker, dotnet, cloud-init]
- `Cloud-init Getting Started`_ [fedora, libvirt, cloud-init]
- `Setup Neovim cloud-init Completion`_
  [neovim, yaml, Language Server Protocol, jsonschema, cloud-init]

Events:

- `cloud-init Summit 2019`_
- `cloud-init Summit 2018`_
- `cloud-init Summit 2017`_


Whitepapers:

- `Utilising cloud-init on Microsoft Azure (Whitepaper)`_
- `Cloud Instance Initialization with cloud-init (Whitepaper)`_

.. _mailing list: https://launchpad.net/~cloud-init
.. _IRC channel on Libera: https://kiwiirc.com/nextclient/irc.libera.chat/cloud-init
.. _validate-yaml.py: https://github.com/canonical/cloud-init/blob/main/tools/validate-yaml.py
.. _Juju: https://ubuntu.com/blog/topics/juju
.. _discourse page: https://discourse.charmhub.io
.. _already do: https://github.com/canonical/ubuntu-advantage-client/blob/9b46480b9e4b88e918bac5ced0d4b8edb3cbbeab/lib/auto_attach.py#L35

.. _cloud-init - The Good Parts: https://www.youtube.com/watch?v=2_m6EUo6VOI
.. _Utilising cloud-init on Microsoft Azure (Whitepaper): https://ubuntu.com/engage/azure-cloud-init-whitepaper
.. _Cloud Instance Initialization with cloud-init (Whitepaper): https://ubuntu.com/blog/cloud-instance-initialisation-with-cloud-init

.. _cloud-init - The cross-cloud Magic Sauce (PDF): https://events.linuxfoundation.org/wp-content/uploads/2017/12/cloud-init-The-cross-cloud-Magic-Sauce-Scott-Moser-Chad-Smith-Canonical.pdf
.. _cloud-init - Building clouds one Linux box at a time (Video): https://www.youtube.com/watch?v=1joQfUZQcPg
.. _cloud-init - Building clouds one Linux box at a time (PDF): https://web.archive.org/web/20181111020605/https://annex.debconf.org/debconf-share/debconf17/slides/164-cloud-init_Building_clouds_one_Linux_box_at_a_time.pdf
.. _Metadata and cloud-init: https://www.youtube.com/watch?v=RHVhIWifVqU
.. _The beauty of cloud-init: https://web.archive.org/web/20180830161317/http://brandon.fuller.name/archives/2011/05/02/06.40.57/
.. _Introduction to cloud-init: http://www.youtube.com/watch?v=-zL3BdbKyGY
.. _Build Azure Devops Agents With Linux cloud-init for Dotnet Development: https://codingsoul.org/2022/04/25/build-azure-devops-agents-with-linux-cloud-init-for-dotnet-development/
.. _Perfect Proxmox Template with Cloud Image and Cloud Init: https://www.youtube.com/watch?v=shiIi38cJe4
.. _Cloud-init Getting Started: https://blog.while-true-do.io/cloud-init-getting-started/
.. _Setup Neovim cloud-init Completion: https://phoenix-labs.xyz/blog/setup-neovim-cloud-init-completion/

.. _cloud-init Summit 2019: https://powersj.io/post/cloud-init-summit19/
.. _cloud-init Summit 2018: https://powersj.io/post/cloud-init-summit18/
.. _cloud-init Summit 2017: https://powersj.io/post/cloud-init-summit17/
.. _Subiquity autoinstaller: https://ubuntu.com/server/docs/install/autoinstall
.. _juju_project: https://discourse.charmhub.io/t/model-config-cloudinit-userdata/512
.. _discourse page: https://discourse.charmhub.io
