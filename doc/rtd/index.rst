.. _index:

cloud-init Documentation
########################

Cloud-init is the *industry standard* multi-distribution method for
cross-platform cloud instance initialization. It is supported across all
major public cloud providers, provisioning systems for private cloud
infrastructure, and bare-metal installations.

On instance boot, cloud-init will identify the cloud it is running on, read
any provided metadata from the cloud, and initialize the system accordingly.
This may involve setting up the network and storage devices, configuring SSH
access keys, and setting up many other aspects of a system. Later,
cloud-init will parse and process any optional user or vendor data that was
passed to the instance.

Getting help
************

Having trouble? We would like to help!

- Check out the :ref:`lxd_tutorial` if you're new to cloud-init
- Try the :ref:`FAQ` for answers to some common questions
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
   topics/code_review.rst
   topics/security.rst
   topics/debugging.rst
   topics/logging.rst
   topics/dir_layout.rst
   topics/analyze.rst
   topics/docs.rst
   topics/testing.rst
   topics/integration_tests.rst

.. vi: textwidth=79
