.. _index:

Cloud-init documentation
########################

``Cloud-init`` is the *industry standard* multi-distribution method for
cross-platform cloud instance initialization. It is supported across all major
public cloud providers, provisioning systems for private cloud infrastructure,
and bare-metal installations.

During boot, ``cloud-init`` identifies the cloud it is running on and
initializes the system accordingly. Cloud instances will automatically be
provisioned during first boot with networking, storage, SSH keys, packages
and various other system aspects already configured.

``Cloud-init`` provides the necessary glue between launching a cloud instance
and connecting to it so that it works as expected.

For cloud users, ``cloud-init`` provides no-install first-boot configuration
management of a cloud instance. For cloud providers, it provides instance setup
that can be integrated with your cloud.

If you would like to read more about what cloud-init is, what it does and how
it works, read our :ref:`high-level introduction<introduction>`.

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

- :ref:`Work through the tutorials<tutorial_index>` if you're new to
  ``cloud-init``
- Use the search bar at the upper left to search the documentation
- :ref:`Read the FAQ<faq>` for answers to some common questions
- Join the conversation at `GitHub Discussions`_
- Find a bug? See :ref:`reporting_bugs`

Project and community
=====================

``Cloud-init`` is an open source project that warmly welcomes community
projects, contributions, suggestions, fixes and constructive feedback.

* Read the `Code of Conduct`_
* Ask questions in the ``#cloud-init`` `room on Matrix <Matrix_>`_
* Follow announcements or ask a question on `GitHub Discussions`_
* :ref:`Contribute on GitHub<development>`
* See the latest `release schedule`_
* See past :ref:`events<summit>`

.. toctree::
   :caption: Documentation
   :hidden:
   :maxdepth: 2

   tutorial/index
   howto/index
   reference/index
   explanation/index


.. toctree::
   :caption: Development
   :hidden:
   :maxdepth: 1

   Develop cloud-init <development/index.rst>

.. LINKS
.. include:: links.txt
.. _release schedule: https://discourse.ubuntu.com/t/2025-cloud-init-release-schedule/55534
