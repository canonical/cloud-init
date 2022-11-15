.. _index:

cloud-init Documentation
########################

Cloud-init is the *industry standard* multi-distribution method for
cross-platform cloud instance initialization.

During boot, cloud-init identifies the cloud it is running on and initializes
the system accordingly. Cloud instances will automatically be provisioned
during first boot with networking, storage, ssh keys, packages and various
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

* `Code of conduct <https://ubuntu.com/community/code-of-conduct>`_
* Ask questions in IRC on ``#cloud-init`` on Libera
* `Mailing list <https://launchpad.net/~cloud-init>`_
* `Contribute on Github <https://github.com/canonical/cloud-init/blob/main/CONTRIBUTING.rst>`_
* `Release schedule <https://discourse.ubuntu.com/search?q=cloud-init%20release%20schedule%20order%3Alatest>`_

Having trouble? We would like to help!
**************************************

- Check out the :ref:`lxd_tutorial` if you're new to cloud-init
- Try the :ref:`FAQ` for answers to some common questions
- Find a bug? `Report bugs on Launchpad <https://bugs.launchpad.net/cloud-init/+filebug>`_

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
