:orphan:

.. _return_codes:

Why did `cloud-init status` start returning exit code 2?
========================================================

Cloud-init introduced :ref:`a new error code<error_codes>`
in 23.4. This page describes the purpose of this change and
gives some context for why this change was made.

.. _return_codes_history:

Background
----------

Since cloud-init provides access to cloud instances, the
paradigm for handling errors was "log errors, but proceed".
Exiting on failure conditions doesn't make sense when that
may prevent one from accessing the system to debug it.

Since cloud-init's behavior is heavily tied to specific cloud
platforms, reproducing cloud-init bugs without exactly
reproducing a specific cloud environment is often impossible,
and often requires guesswork. To make debugging cloud-init
possible without reproducing exactly, cloud-init logs are
quite verbose.

.. _return_codes_pain_points:

Pain points
-----------

1) Invalid configurations were historically ignored.
2) Log verbosity is unfriendly to end users that may not know
   what to look for. Verbose logs means users often ignore real
   errors.
3) Cloud-init's reported status was only capable of telling the user
   whether cloud-init crashed. Cloud-init would report a status of
   "done" in the following cases:

   * a user's configuration was invalid
   * if the operating system or cloud environment experienced some error that
     prevented cloud-init from configuring the instance
   * if cloud-init internally experienced an error - all of these previously
     reported a status of "done".

.. _return_codes_improvements:

Efforts to improve cloud-init
-----------------------------

Several changes have been introduced to cloud-init to address the pain
points described above.

JSON schema
^^^^^^^^^^^

Cloud-init has defined a JSON schema which fully documents the user-data
cloud-config. This JSON schema may be used in several different ways:

Text editor integration
"""""""""""""""""""""""

Thanks to `yaml-language-server`_, cloud-init's JSON schema may be
used for YAML syntax checking, warnings when invalid keys are used, and
autocompletion. Several different text editors are capable of this.
See this `blog post on configuring this for neovim`_, or for VScode one
can install the `extension`_ and then a file named ``cloud-config.yaml``
will automatically use cloud-init's JSON schema.


Cloud-init schema subcommand
""""""""""""""""""""""""""""

The cloud-init package includes a cloud-init subcommand,
:ref:`cloud-init schema<check_user_data_cloud_config>` which uses the schema
to validate either the configuration passed to the instance that you are
running the command on, or to validate an arbitrary text file containing a
configuration.

Return codes
^^^^^^^^^^^^

Cloud-init historically used two return codes from the
:code:`cloud-init status` subcommand: 0 to indicate success and 1 to indicate
failure. These return codes lacked nuance. Return code 0 (success) included
the in-between when something went wrong, but cloud-init was able to finish.

Many users of cloud-init run :code:`cloud-init status --wait` and expect that
when complete, cloud-init has finished. Since cloud-init is not guaranteed to
succeed, users should also be check the return code of this command.

As of 23.4, errors that do not crash cloud-init will have an exit code of 2.
Exit code of 1 means that cloud-init crashed, and an exit code 0 more correctly
means that cloud-init succeeded. Anyone that previously checked for exit code 0
should probably update their assumptions in one of the following two ways:

Users that wish to take advantage of cloud-init's error reporting
capabilities should check for exit code of 2 from :code:`cloud-init status`.
An example of this:

.. code-block:: python

    from logging import getLogger
    from json import loads
    from subprocess import run
    from sys import exit

    logger = getLogger(__name__)
    completed = run("cloud-init status --format json")
    output = loads(completed.stdout)

    if 2 == completed.return_code:
        # something bad might have happened - we should check it out
        logger.warning("cloud-init experienced a recoverable error")
        logger.warning("status: %s", output.get("extended_status"))
        logger.warning("recoverable error: %s", output.get("recoverable_errors"))

    elif 1 == completed.return_code:
        # cloud-init completely failed
        logger.error("cloud-init crashed, all bets are off!")
        exit(1)

Users that wish to use ignore cloud-init's errors and check the return code in
a backwards-compatible way should check that the return code is not equal to
1. This will provide the same behavior before and after the changed exit code.
See an example of this:

.. code-block:: python

    from logging import getLogger
    from subprocess import run
    from sys import exit

    logger = getLogger(__name__)
    completed = run("cloud-init status --format json")

    if 1 == completed.return_code:
        # cloud-init completely failed
        logger.error("cloud-init crashed, all bets are off!")
        exit(1)

    # cloud-init might have failed, but this code ignores that possibility
    # in preference of backwards compatibility

See :ref:`our explanation of failure states<failure_states>` for more
information.

.. _yaml-language-server: https://github.com/redhat-developer/yaml-language-server
.. _extension: https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml
.. _blog post on configuring this for neovim: https://phoenix-labs.xyz/blog/setup-neovim-cloud-init-completion/
