.. _about-cloud-config:

About the cloud-config file
***************************

The ``#cloud-config`` file is a type of user data that cloud-init can consume
to automatically set up various aspects of the system.

It overrides all other types of user data, so if there is a conflict between
the config you specify in other :ref:`user data formats <user_data_formats>`,
the contents of the ``#cloud-config`` file will take precendence.

Note that networks are not configurable via the ``#cloud-config`` file because
:ref:`network configuration <network_config>` occurs before user data is
consumed and applied.

How do I create a cloud-config file?
====================================

The cloud-config file can be written in any valid YAML but the first line
**must start** with ``#cloud-config``. This line identifies the file to
cloud-init and ensures that it will be processed as intended.

After the first line, every aspect of the system's configuration is controlled
through specific cloud-init **modules**. Each module included in the
``cloud-config`` file can be thought of as a section.

Let us consider the example of the "keyboard" module. The module has a
corresponding top-level key (``keyboard:``, in this case), and beneath that
the various configuration parameters are defined:

.. code-block:: yaml

   keyboard:
     layout: us
     model: pc105
     variant: nodeadkeys
     options: compose:rwin

A full list of modules can be found :ref:`on our modules page <modules>`. This
list also shows the valid schema keys for every module, and YAML examples.

Module ordering
---------------

The order of the different module "sections" is mostly unimportant and modules
can be shown in any order -- except where there are dependencies. For example,
if you want to create users and also put them in a specific group, then the
``groups`` section must go before ``users`` so that the groups are created
first.

Cloud-config for the live installer
-----------------------------------

For the special case where your cloud-config file is will be consumed by the
Ubuntu installer, you will need to include the the ``autoinstall:``
top level key. The presence of this key will instruct cloud-init not to process
the user-data itself, but instead to pass it directly to the installer for
processing.

For more detailed instructions for this case, refer to the installer
documentation on using `cloud-init with the autoinstaller`_.

Checking your cloud-config file
===============================

Once you have constructed your cloud-config file, you can check it against
the :ref:`cloud-config validation tool <check_user_data_cloud_config>`. This
tool tests the YAML in your file against the cloud-init schema and will warn
you of any errors.

Example cloud-config file
=========================

The following code is an example of a working user data cloud-config file.
The :ref:`cloud-config example library <yaml_examples>` contains further
examples that can be copy/pasted and adapted to your needs.

.. code-block:: yaml

   #cloud-config
   <put example cloud-config here>

.. LINKS
.. _cloud-init with the autoinstaller: https://canonical-subiquity.readthedocs-hosted.com/en/latest/tutorial/providing-autoinstall.html#autoinstall-by-way-of-cloud-config
