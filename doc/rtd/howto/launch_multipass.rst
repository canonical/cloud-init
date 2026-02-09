.. _launch_multipass:

Run cloud-init locally with multipass
*************************************

`Multipass`_ is a cross-platform tool for launching Ubuntu VMs across Linux,
Windows, and macOS.

When launching a Multipass VM, user-data can be passed by adding the
``--cloud-init`` flag and an appropriate YAML file containing the user-data.
For more information about cloud-config, see
:ref:`the explanatory guide <user_data_formats-cloud_config>`.

Create your configuration
-------------------------

.. include:: shared/create_config.txt

Launch your instance
--------------------

You can pass the ``user-data`` file to Multipass and launch a Bionic instance
named ``test-vm`` with the following command:

.. code-block:: shell-session

    $ multipass launch bionic --name test-vm --cloud-init user-data

Multipass will validate the ``user-data`` configuration file before starting
the VM. This breaks all cloud-init configuration formats except the *user-data
cloud-config*.

.. LINKS
.. _Multipass: https://multipass.run/

