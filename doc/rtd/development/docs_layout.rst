.. _docs_layout:

Documentation directory layout
******************************

Cloud-init's documentation directory structure, with respect to the root
directory:

.. code-block:: text

    /doc/
        - examples/
        - man/
        - rtd/
            - tutorial/
            - howto/
            - explanation/
            - reference/

            - development/
            - static/
                - css/
                - js/
                - *logos*
            - *conf.py*
            - *index.rst*
            - *links.txt*
        - rtd_html/
        - sources/


``examples/``
=============


``man/``
========

This subdirectory contains the Linux man pages for the binaries provided
by cloud-init.


``rtd/``
========

This subdirectory is of most interest to anyone who wants to create or update
either the content of the documentation, or the styling of it.

* The content of the documentation is organised according to the `Diataxis`_
  framework and can be found in the subdirectories: ``tutorial/``, ``howto/``,
  ``explanation/``, and ``reference/``.

* The ``development/`` subdirectory contains documentation for contributors.

* ``static/`` contains content that relates to the styling of the documentation
  in the form of custom CSS or javascript files found in ``css/`` and ``js/``
  respectively. This is also where you can find the cloud-init logo.

* ``conf.py`` contains Sphinx configuration commands.
* ``index.rst`` is the front page of the documentation.
* ``links.txt`` contains common (and reusable) links so that you do not need to
  define the same URLs on every page and can use a more convenient shorthand
  when referencing often-used links.

``rtd_html/``
=============

When the documentation is built locally using ``tox -e doc``, the built pages
can be found in this folder.

``sources/``
============

This subdirectory contains demos which can help the reader understand
how parts of the product work.

.. LINKS

.. include:: ../links.txt
