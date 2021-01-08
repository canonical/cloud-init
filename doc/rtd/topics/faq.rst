.. _faq:

FAQ
***

How do I get help?
==================

Having trouble? We would like to help!

- First go through this page with answers to common questions
- Use the search bar at the upper left to search these docs
- Ask a question in the ``#cloud-init`` IRC channel on Freenode
- Join and ask questions on the `cloud-init mailing list <https://launchpad.net/~cloud-init>`_
- Find a bug? Check out the :ref:`reporting_bugs` topic for
  how to report one

Where are the logs?
===================

Cloud-init uses two files to log to:

- `/var/log/cloud-init-output.log`: captures the output from each stage of
  cloud-init when it runs
- `/var/log/cloud-init.log`: very detailed log with debugging output,
  detailing each action taken
- `/run/cloud-init`: contains logs about how cloud-init decided to enable or
  disable itself, as well as what platforms/datasources were detected. These
  logs are most useful when trying to determine what cloud-init ran or did not
  run.

Be aware that each time a system boots, new logs are appended to the files in
`/var/log`. Therefore, the files may have more than one boot worth of
information present.

When reviewing these logs look for any errors or Python tracebacks to check
for any errors.

Where are the configuration files?
==================================

Cloud-init config is provided in two places:

- `/etc/cloud/cloud.cfg`
- `/etc/cloud/cloud.cfg.d/*.cfg`

These files can define the modules that run during instance initialization,
the datasources to evaluate on boot, and other settings.

Where are the data files?
=========================

Inside the `/var/lib/cloud/` directory there are two important subdirectories:

instance
--------

The `/var/lib/cloud/instance` directory is a symbolic link that points
to the most recenlty used instance-id directory. This folder contains the
information cloud-init received from datasources, including vendor and user
data. This can be helpful to review to ensure the correct data was passed.

It also contains the `datasource` file that containers the full information
about what datasource was identified and used to setup the system.

Finally, the `boot-finished` file is the last thing that cloud-init does.

data
----

The `/var/lib/cloud/data` directory contain information related to the
previous boot:

* `instance-id`: id of the instance as discovered by cloud-init. Changing
  this file has no effect.
* `result.json`: json file will show both the datasource used to setup
  the instance, and if any errors occured
* `status.json`: json file shows the datasource used and a break down
  of all four modules if any errors occured and the start and stop times.

What datasource am I using?
===========================

To correctly setup an instance, cloud-init must correctly identify the
cloud that it is on. Therefore knowing what datasource is used on an
instance launch can help aid in debugging.

To find what datasource is getting used run the `cloud-id` command:

.. code-block:: shell-session

    $ cloud-id
    nocloud

If the cloud-id is not what is expected, then running the `ds-identify`
script in debug mode and providing that in a bug can help aid in resolving
any issues:

.. code-block:: shell-session

    $ sudo DEBUG_LEVEL=2 DI_LOG=stderr /usr/lib/cloud-init/ds-identify --force

The force parameter allows the command to be run again since the instance has
already launched. The other options increase the verbosity of logging and
put the logs to STDERR.

How can I re-run datasource detection and cloud-init?
=====================================================

If a user is developing a new datasource or working on debugging an issue it
may be useful to re-run datasource detection and the initial setup of
cloud-init.

To do this, force ds-identify to re-run, clean up any logs, and re-run
cloud-init:

.. code-block:: shell-session

  $ sudo DI_LOG=stderr /usr/lib/cloud-init/ds-identify --force
  $ sudo cloud-init clean --logs
  $ sudo cloud-init init --local
  $ sudo cloud-init init

.. warning::

    These commands will re-run cloud-init as if this were first boot of a
    system: this will, at the very least, cycle SSH host keys and may do
    substantially more.  Do not run these commands on production systems.

How can I debug my user data?
=============================

Two of the most common issues with user data, that also happens to be
cloud-config is:

1. Incorrectly formatted YAML
2. First line does not contain `#cloud-config`

To verify your YAML, we do have a short script called `validate-yaml.py`_
that can validate your user data offline.

.. _validate-yaml.py: https://github.com/canonical/cloud-init/blob/master/tools/validate-yaml.py

Another option is to run the following on an instance to debug userdata
provided to the system:

.. code-block:: shell-session

    $ cloud-init devel schema --system --annotate

As launching instances in the cloud can cost money and take a bit longer,
sometimes it is easier to launch instances locally using Multipass or LXD:

Multipass
---------

`Multipass`_ is a cross-platform tool to launch Ubuntu VMs across Linux,
Windows, and macOS.

When a user launches a Multipass VM, user data can be passed by adding the
`--cloud-init` flag and the appropriate YAML file containing user data:

.. code-block:: shell-session

    $ multipass launch bionic --name test-vm --cloud-init userdata.yaml

Multipass will validate the YAML syntax of the cloud-config file before
attempting to start the VM! A nice addition to help save time when
experimenting with launching instances with various cloud-configs.

Multipass only supports passing user-data and only as YAML cloud-config
files. Passing a script, a MIME archive, or any of the other user-data
formats cloud-init supports will result in an error from the YAML syntax
validator.

.. _Multipass: https://multipass.run/

LXD
---

`LXD`_ offers a streamlined user experience for using linux system
containers. With LXD, a user can pass:

* user data
* vendor data
* metadata
* network configuration

The following initializes a container with user data:

.. code-block:: shell-session

    $ lxc init ubuntu-daily:bionic test-container
    $ lxc config set test-container user.user-data - < userdata.yaml
    $ lxc start test-container

To avoid the extra commands this can also be done at launch:

.. code-block:: shell-session

    $ lxc launch ubuntu-daily:bionic test-container --config=user.user-data="$(cat userdata.yaml)"

Finally, a profile can be setup with the specific data if a user needs to
launch this multiple times:

.. code-block:: shell-session

    $ lxc profile create dev-user-data
    $ lxc profile set dev-user-data user.user-data - < cloud-init-config.yaml
    $ lxc launch ubuntu-daily:bionic test-container -p default -p dev-user-data

The above examples all show how to pass user data. To pass other types of
configuration data use the config option specified below:

+----------------+---------------------+
| Data           | Config Option       |
+================+=====================+
| user data      | user.user-data      |
+----------------+---------------------+
| vendor data    | user.vendor-data    |
+----------------+---------------------+
| metadata       | user.meta-data      |
+----------------+---------------------+
| network config | user.network-config |
+----------------+---------------------+

See the LXD `Instance Configuration`_ docs for more info about configuration
values or the LXD `Custom Network Configuration`_ document for more about
custom network config.

.. _LXD: https://linuxcontainers.org/
.. _Instance Configuration: https://linuxcontainers.org/lxd/docs/master/instances
.. _Custom Network Configuration: https://linuxcontainers.org/lxd/docs/master/cloud-init

cloud-localds
-------------

The `cloud-localds` command from the `cloud-utils`_ package generates a disk
with user supplied data. The NoCloud datasouce allows users to provide their
own user data, metadata, or network configuration directly to an instance
without running a network service. This is helpful for launching local cloud
images with QEMU for example.

The following is an example of creating the local disk using the cloud-localds
command:

.. code-block:: shell-session

    $ cat >user-data <<EOF
    #cloud-config
    password: password
    chpasswd:
      expire: False
    ssh_pwauth: True
    ssh_authorized_keys:
      - ssh-rsa AAAA...UlIsqdaO+w==
    EOF
    $ cloud-localds seed.img user-data

The resulting seed.img can then get passed along to a cloud image containing
cloud-init. Below is an example of passing the seed.img with QEMU:

.. code-block:: shell-session

    $ qemu-system-x86_64 -m 1024 -net nic -net user \
        -hda ubuntu-20.04-server-cloudimg-amd64.img \
        -hdb seed.img

The now booted image will allow for login using the password provided above.

For additional configuration, users can provide much more detailed
configuration, including network configuration and metadata:

.. code-block:: shell-session

    $ cloud-localds --network-config=network-config-v2.yaml \
      seed.img userdata.yaml metadata.yaml

See the :ref:`network_config_v2` page for details on the format and config of
network configuration. To learn more about the possible values for metadata,
check out the :ref:`nocloud` page.

.. _cloud-utils: https://github.com/canonical/cloud-utils/

Where can I learn more?
========================================

Below are some videos, blog posts, and white papers about cloud-init from a
variety of sources.

- `cloud-init - The Good Parts`_
- `cloud-init Summit 2019`_
- `Utilising cloud-init on Microsoft Azure (Whitepaper)`_
- `Cloud Instance Initialization with cloud-init (Whitepaper)`_
- `cloud-init Summit 2018`_
- `cloud-init - The cross-cloud Magic Sauce (PDF)`_
- `cloud-init Summit 2017`_
- `cloud-init - Building clouds one Linux box at a time (Video)`_
- `cloud-init - Building clouds one Linux box at a time (PDF)`_
- `Metadata and cloud-init`_
- `The beauty of cloud-init`_
- `Introduction to cloud-init`_

.. _cloud-init - The Good Parts: https://www.youtube.com/watch?v=2_m6EUo6VOI
.. _cloud-init Summit 2019: https://powersj.io/post/cloud-init-summit19/
.. _Utilising cloud-init on Microsoft Azure (Whitepaper): https://ubuntu.com/engage/azure-cloud-init-whitepaper
.. _Cloud Instance Initialization with cloud-init (Whitepaper): https://ubuntu.com/blog/cloud-instance-initialisation-with-cloud-init
.. _cloud-init Summit 2018: https://powersj.io/post/cloud-init-summit18/
.. _cloud-init - The cross-cloud Magic Sauce (PDF): https://events.linuxfoundation.org/wp-content/uploads/2017/12/cloud-init-The-cross-cloud-Magic-Sauce-Scott-Moser-Chad-Smith-Canonical.pdf
.. _cloud-init Summit 2017: https://powersj.io/post/cloud-init-summit17/
.. _cloud-init - Building clouds one Linux box at a time (Video): https://www.youtube.com/watch?v=1joQfUZQcPg
.. _cloud-init - Building clouds one Linux box at a time (PDF): https://annex.debconf.org/debconf-share/debconf17/slides/164-cloud-init_Building_clouds_one_Linux_box_at_a_time.pdf
.. _Metadata and cloud-init: https://www.youtube.com/watch?v=RHVhIWifVqU
.. _The beauty of cloud-init: http://brandon.fuller.name/archives/2011/05/02/06.40.57/
.. _Introduction to cloud-init: http://www.youtube.com/watch?v=-zL3BdbKyGY

.. vi: textwidth=79
