.. _index:

cloud-init Documentation
########################

Cloud-init is the *industry standard* multi-distribution method for
cross-platform cloud instance initialization. It is supported across all major
public cloud providers, provisioning systems for private cloud infrastructure,
and bare-metal installations.

During boot, cloud-init identifies the cloud it is running on and initializes
the system accordingly. Cloud instances will automatically be provisioned
during first boot with networking, storage, SSH keys, packages and various
other system aspects already configured.

Cloud-init provides the necessary glue between launching a cloud instance and
connecting to it so that it works as expected.

For cloud users, cloud-init provides no-install first-boot configuration
management of a cloud instance. For cloud providers, it provides instance setup
that can be integrated with your cloud.

Project and community
*********************
Cloud-init is an open source project that warmly welcomes community
projects, contributions, suggestions, fixes and constructive feedback.

* Read our `Code of conduct`_
* Ask questions in the ``#cloud-init`` `IRC channel on Libera`_
* Join the `cloud-init mailing list`_
* `Contribute on Github`_
* `Release schedule`_

Having trouble? We would like to help!
**************************************

- Check out the :ref:`lxd_tutorial` if you're new to cloud-init
- Try the :ref:`FAQ` for answers to some common questions
- You can also search the cloud-init `mailing list archive`_
- Find a bug? `Report bugs on Launchpad`_

.. toctree::
   :hidden:
   :titlesonly:
   :caption: Getting Started

   topics/tutorial.rst
   topics/availability.rst
   topics/boot.rst
   topics/cli.rst
   topics/faq.rst
   topics/bugs.rst

.. toctree::
   :hidden:
   :titlesonly:
   :caption: Explanation

   topics/configuration.rst

.. toctree::
   :hidden:
   :titlesonly:
   :caption: User Data

   topics/format.rst
   topics/examples.rst
   topics/events.rst
   topics/merging.rst

.. toctree::
   :hidden:
   :titlesonly:
   :caption: Instance Data

   topics/instancedata.rst
   topics/datasources.rst
   topics/vendordata.rst
   topics/network-config.rst

.. toctree::
   :hidden:
   :titlesonly:
   :caption: Reference

   topics/base_config_reference.rst
   topics/modules.rst

.. toctree::
   :hidden:
   :titlesonly:
   :caption: Development

   topics/contributing.rst
   topics/module_creation.rst
   topics/code_review.rst
   topics/security.rst
   topics/debugging.rst
   topics/logging.rst
   topics/dir_layout.rst
   topics/analyze.rst
   topics/docs.rst
   topics/testing.rst
   topics/integration_tests.rst
.. LINKS
.. _Code of conduct: https://ubuntu.com/community/code-of-conduct
.. _IRC channel on Libera: https://kiwiirc.com/nextclient/irc.libera.chat/cloud-init
.. _cloud-init mailing list: https://launchpad.net/~cloud-init
.. _mailing list archive: https://lists.launchpad.net/cloud-init/
.. _Contribute on Github: https://cloudinit.readthedocs.io/en/latest/topics/contributing.html
.. _Release schedule: https://discourse.ubuntu.com/t/cloud-init-2022-release-schedule/25413
.. _Report bugs on Launchpad: https://bugs.launchpad.net/cloud-init/+filebug
