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
it works, check out our :ref:`high-level introduction<introduction>`
to the tool.

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
- You can also check `Github Discussions`_
- Find a bug? `Report bugs on GitHub Issues`_

Project and community
=====================

``Cloud-init`` is an open source project that warmly welcomes community
projects, contributions, suggestions, fixes and constructive feedback.

* Read our `Code of Conduct`_
* Ask questions in the ``#cloud-init`` `room on Matrix <Matrix_>`_
* Follow announcements or ask a question on `GitHub Discussions`_
* :ref:`Contribute on GitHub<contributing>`
* `Release schedule`_

.. toctree::
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

   Contributing overview <development/index.rst>
   Contribute to code <development/contribute_code.rst>
   Contribute to docs <development/contribute_docs.rst>
   Community <development/summit.rst>
   Downstream packaging <development/packaging.rst>


.. LINKS
.. include:: links.txt
.. _Release schedule: https://discourse.ubuntu.com/t/2025-cloud-init-release-schedule/55534
.. _Report bugs on GitHub Issues: https://github.com/canonical/cloud-init/issues
