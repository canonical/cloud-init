.. _index:

cloud-init Documentation
########################

Cloud-init is the *industry standard* multi-distribution method for
cross-platform cloud instance initialization.

During boot, cloud-init identifies the cloud it is running on, reads
metadata from the cloud, and initializes the system accordingly.

Cloud-init allows users to boot instances that are automatically
provisioned during first boot with networking, storage, ssh keys, packages and
various other system aspects already configured.

This project is for anyone that wishes to bring up an instance that configures
itself during boot.


Having trouble? We would like to help!
**************************************

- Check out the :ref:`lxd_tutorial` if you're new to cloud-init
- Try the :ref:`FAQ` for answers to some common questions
- Have a feature idea or bug to fix? `Contribute on Github <https://github.com/canonical/cloud-init>`_
- Ask a question in the ``#cloud-init`` IRC channel on Libera
- Join and ask questions on the `cloud-init mailing list <https://launchpad.net/~cloud-init>`_
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
   :caption: User Data

   topics/format.rst
   topics/examples.rst
   topics/events.rst
   topics/modules.rst
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
