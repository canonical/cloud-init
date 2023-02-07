.. _index:

Cloud-init documentation
########################

``Cloud-init`` is the *industry standard* multi-distribution method for
cross-platform cloud instance initialisation. It is supported across all major
public cloud providers, provisioning systems for private cloud infrastructure,
and bare-metal installations.

During boot, ``cloud-init`` identifies the cloud it is running on and
initialises the system accordingly. Cloud instances will automatically be
provisioned during first boot with networking, storage, SSH keys, packages
and various other system aspects already configured.

``Cloud-init`` provides the necessary glue between launching a cloud instance
and connecting to it so that it works as expected.

For cloud users, ``cloud-init`` provides no-install first-boot configuration
management of a cloud instance. For cloud providers, it provides instance setup
that can be integrated with your cloud.

-----

.. grid:: 1 1 2 2
   :gutter: 3

   .. grid-item-card:: **Tutorials**
       :link: tutorial/index
       :link-type: doc

       Get started - a hands-on introduction to ``cloud-init`` for new users

   .. grid-item-card:: **How-to guides**
       :link: howto/index
       :link-type: doc

       Step-by-step guides covering key operations and common tasks

.. grid:: 1 1 2 2
   :gutter: 3
   :reverse:

   .. grid-item-card:: **Reference**
       :link: reference/index
       :link-type: doc

       Technical information - specifications, APIs, architecture

   .. grid-item-card:: **Explanation**
       :link: explanation/index
       :link-type: doc

       Discussion and clarification of key topics

-----

Having trouble? We would like to help!
======================================

- :ref:`Check out our tutorials<tutorial_index>` if you're new to
  ``cloud-init``
- :ref:`Try the FAQ<faq>` for answers to some common questions
- You can also search the ``cloud-init`` `mailing list archive`_
- Find a bug? `Report bugs on Launchpad`_

Project and community
=====================

``Cloud-init`` is an open source project that warmly welcomes community
projects, contributions, suggestions, fixes and constructive feedback.

* Read our `Code of Conduct`_
* Ask questions in the ``#cloud-init`` `IRC channel on Libera`_
* Join the `cloud-init mailing list`_
* :ref:`Contribute on GitHub<contributing>`
* `Release schedule`_

.. toctree::
   :hidden:
   :maxdepth: 2

   tutorial/index
   howto/index
   explanation/index
   reference/index
   development/index


.. LINKS
.. _Code of Conduct: https://ubuntu.com/community/code-of-conduct
.. _IRC channel on Libera: https://kiwiirc.com/nextclient/irc.libera.chat/cloud-init
.. _cloud-init mailing list: https://launchpad.net/~cloud-init
.. _mailing list archive: https://lists.launchpad.net/cloud-init/
.. _Release schedule: https://discourse.ubuntu.com/t/cloud-init-release-schedule/32244
.. _Report bugs on Launchpad: https://bugs.launchpad.net/cloud-init/+filebug
