.. _about-cloud-config:

About the cloud-config file
***************************

The ``#cloud-config`` file is a type of user-data that cloud-init can consume
to automatically set up various aspects of the system. It is commonly referred
to as **cloud config**. Using cloud config to configure your machine leverages
the best practices encoded into cloud-init's modules in a distribution-agnostic
way.

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

Most modules are specified through the use of one or more **top-level keys**,
and the configuration options are set using YAML key-value pairs or list types,
according to the config schema. It follows this general format:

.. code-block:: yaml

   #cloud-config
   top-level-key:
     config-key-1: config-value-1
     config-key-2: config-value-2
     list-type:
     - list-value-1
       additional-list-value-1
     - list-value-2

The order of the top-level keys is unimportant -- they can be written in any
order, and cloud-init handles the order of operations.

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

Not all modules require a top-level key, and will run on the system anyway if
certain conditions are met. A full list of modules can be found
:ref:`on our modules page <modules>`. This list also shows the valid schema for
every module, and simple YAML examples.

Checking your cloud-config file
===============================

Once you have constructed your cloud-config file, you can check it against
the :ref:`cloud-config validation tool <check_user_data_cloud_config>`. This
tool tests the YAML in your file against the cloud-init schema and will warn
you of any errors.

Example cloud-config file
=========================

The following code is an example of a complete user-data cloud-config file.
The :ref:`cloud-config example library <yaml_examples>` contains further
examples that can be copy/pasted and adapted to your needs.

.. code-block:: yaml

   #cloud-config

   # Basic system setup
   hostname: example-host
   fqdn: example-host.example.com

   # User setup configuration
   users:
     - name: exampleuser
       gecos: Example User
       sudo: ['ALL=(ALL) NOPASSWD:ALL']
       groups: sudo
       homedir: /home/exampleuser
       shell: /bin/bash
       ssh_authorized_keys:
         - ssh-rsa AAAAB3...restofpublickey user@host

   # Change passwords for exampleuser using chpasswd
   chpasswd:
     expire: false
     users:
     - {name: exampleuser, password: terriblepassword12345, type: text}

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
.. _YAML version 1.1: https://yaml.org/spec/1.1/current.html
