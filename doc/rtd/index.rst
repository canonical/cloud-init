.. _index:

cloud-init Documentation
########################

Cloud-init is the *industry standard* multi-distribution method for
cross-platform cloud instance initialization. It is supported across all
major public cloud providers, provisioning systems for private cloud
infrastructure, and bare-metal installations.

Cloud instances are initialized from a disk image and instance data:

- Cloud metadata
- User data (optional)
- Vendor data (optional)

Cloud-init will identify the cloud it is running on during boot, read any
provided metadata from the cloud and initialize the system accordingly. This
may involve setting up the network and storage devices to configuring SSH
access key and many other aspects of a system. Later on the cloud-init will
also parse and process any optional user or vendor data that was passed to the
instance.

Getting help
************

Having trouble? We would like to help!

- Try the :ref:`FAQ` – its got answers to some common questions
- Ask a question in the ``#cloud-init`` IRC channel on Freenode
- Join and ask questions on the `cloud-init mailing list <https://launchpad.net/~cloud-init>`_
- Find a bug? `Report bugs on Launchpad <https://bugs.launchpad.net/cloud-init/+filebug>`_

.. toctree::
   :hidden:
   :titlesonly:
   :caption: Getting Started

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

   topics/hacking.rst
   topics/code_review.rst
   topics/security.rst
   topics/debugging.rst
   topics/logging.rst
   topics/dir_layout.rst
   topics/analyze.rst
   topics/docs.rst
   topics/integration_tests.rst
   topics/cloud_tests.rst

.. vi: textwidth=79
