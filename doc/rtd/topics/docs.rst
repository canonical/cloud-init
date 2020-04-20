.. _docs:

Docs
****

These docs are hosted on Read the Docs. The following will explain how to
contribute to and build these docs locally.

The documentation is primarily written in reStructuredText.


Building
========

There is a makefile target to build the documentation for you:

.. code-block:: shell-session

    $ tox -e doc

This will do two things:

- Build the documentation using sphinx
- Run doc8 against the documentation source code

Once build the HTML files will be viewable in ``doc/rtd_html``. Use your
web browser to open ``index.html`` to view and navigate the site.

Style Guide
===========

Headings
--------
The headings used across the documentation use the following hierarchy:

- ``*****``: used once atop of a new page
- ``=====``: each sections on the page
- ``-----``: subsections
- ``^^^^^``: sub-subsections
- ``"""""``: paragraphs

The top level header ``######`` is reserved for the first page.

If under and overline are used, their length must be identical. The length of
the underline must be at least as long as the title itself

Line Length
-----------
Please keep the line lengths to a maximum of **79** characters. This ensures
that the pages and tables do not get too wide that side scrolling is required.

Header
------
Adding a link at the top of the page allows for the page to be referenced by
other pages. For example for the FAQ page this would be:

.. code-block:: rst

    .. _faq:

Footer
------
The footer should include the textwidth

.. code-block:: rst

    .. vi: textwidth=79

Vertical Whitespace
-------------------
One newline between each section helps ensure readability of the documentation
source code.

Common Words
------------
There are some common words that should follow specific usage:

- ``cloud-init``: always lower case with a hyphen, unless starting a sentence
  in which case only the 'C' is capitalized (e.g. ``Cloud-init``).
- ``metadata``: one word
- ``user data``: two words, not to be combined
- ``vendor data``: like user data, it is two words

.. vi: textwidth=79
