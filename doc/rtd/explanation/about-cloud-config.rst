.. _about-cloud-config:

About the cloud-config file
***************************

The ``#cloud-config`` file is a type of user data that cloud-init can consume
to automatically set up various aspects of the system. It is the preferred way
to pass this type of configuration to cloud-init, and is commonly referred to
as "cloud config". 

Note that networks are not configurable via the ``#cloud-config`` file because
:ref:`network configuration <network_config>` comes from the cloud.

How do I create a cloud-config file?
====================================

The cloud-config file uses `YAML version 1.1`_. The file is composed of a
**header** and one or more **modules**.

* **The header**:
  The first line **must start** with ``#cloud-config``. This line identifies
  the file to cloud-init and ensures that it will be processed as intended.

* **The modules**:
  After the header, every aspect of the system's configuration is controlled
  through specific cloud-init modules.

Each module is declared through the use of its **top-level key**, and the
configuration options are set using key-value pairs (or list keys) according
to the config schema. It follows this general format:

.. code-block:: yaml

   #cloud-config
   top-level-key:   
     config-key-1: config-value-1
     config-key-2: config-value-2
     list-key:
     - list-value-1
       additional-list-value-1
     - list-value-2

Let us consider a real example using the :ref:`Keyboard <mod_cc_keyboard>`
module. The top-level key for this module is ``keyboard:``, and beneath that
are the various configuration options for the module shown as key-value pairs:

.. code-block:: yaml

   #cloud-config
   keyboard:
     layout: us
     model: pc105
     variant: nodeadkeys
     options: compose:rwin

A full list of modules can be found :ref:`on our modules page <modules>`. This
list also shows the valid schema keys for every module, and YAML examples.

Module ordering
---------------

The order of the ``cloud-config`` keys is unimportant and modules can be
written in any order.

.. note::
   The :ref:`Users and Groups <mod_cc_users_groups>` module is a special case
   where ordering matters if you want to add users to a group list.

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

The following code is an example of a complete user data cloud-config file.
The :ref:`cloud-config example library <yaml_examples>` contains further
examples that can be copy/pasted and adapted to your needs.

.. code-block:: yaml

   #cloud-config

   # Basic system setup
   hostname: example-host
   fqdn: example-host.example.com

   # Configure storage
   storage:
     files:
       - path: /etc/example_file.txt
         content: |
           Some text to be stored in the file
       - path: /etc/example_script.txt
         content: |
           #!/bin/bash
           echo "Some text to be run in the script"

   # User setup configuration
   users:
     - name: exampleuser
       gecos: Example User
       sudo: ['ALL=(ALL) NOPASSWD:ALL']
       groups: sudo
       home: /home/exampleuser
       shell: /bin/bash
       ssh_authorized_keys:
         - ssh-rsa AAAAB3...restofpublickey user@host

   # Change passwords using chpasswd
   chpasswd:
     exampleuser: terriblepassword12345

   # Package management
   package_update: true
   package_upgrade: true
   packages:
     - git
     - nginx
     - python3

   # Commands to run at the end of the cloud-init process
   runcmd:
     - echo "Hello, world!" > /etc/motd
     - systemctl restart nginx
     - mkdir -p /var/www/html
     - echo "<html><body><h1>Welcome to the party, pal!</h1></body></html>" > /var/www/html/index.html

   # Write files to the instance
   write_files:
     - path: /etc/example_config.conf
       content: |
         [example-config]
         key=value
     - path: /etc/motd
       content: |
         Some text that will appear in your MOTD!

   # Final message, shown after cloud-init completes
   final_message: "The system is up, after $UPTIME seconds"

   # Reboot the instance after configuration
   power_state:
     mode: reboot
     message: Rebooting after initial setup
     timeout: 30
     condition: True

.. LINKS
.. _cloud-init with the autoinstaller: https://canonical-subiquity.readthedocs-hosted.com/en/latest/tutorial/providing-autoinstall.html#autoinstall-by-way-of-cloud-config
.. _YAML version 1.1: https://yaml.org/spec/1.1/current.html
