.. _docs:

Documentation
*************

These docs are hosted on `Read the Docs`_. The following will explain how to
contribute to, and build, these docs locally.

The documentation is primarily written in reStructuredText, with some pages
written in standard Markdown.

Building
========

There is a makefile target to build the documentation for you:

.. code-block:: shell-session

    $ tox -e doc

This will do two things:

- Build the documentation using sphinx.
- Run doc8 against the documentation source code.

Once built, the HTML files will be viewable in `doc/rtd_html`. Use your
web browser to open `index.html` to view and navigate the site.

Style guide
===========

Language
--------

Where possible, text should be written in UK English. However, discretion and
common sense can both be applied. For example, where text refers to code
elements that exist in US English, the spelling of these elements should not
be changed to UK English.

Headings
--------

In reStructuredText, headings are denoted using symbols to underline the text.
The headings used across the documentation use the following hierarchy:

- ``#####``: Top level header (reserved for the main index page)
- ``*****``: Title header (used once at the top of a new page)
- ``=====``: Section headers
- ``-----``: Subsection headers
- ``^^^^^``: Sub-subsection headers
- ``"""""``: Paragraphs

The length of the underline must be at least as long as the title itself.

Ensure that you do not skip header levels when creating your document
structure, i.e., that a section is followed by a subsection, and not a
sub-subsection.

Line length
-----------

Please keep the line lengths to a maximum of **79** characters. This ensures
that the pages and tables do not get so wide that side scrolling is required.

Anchor labels
-------------

Adding an anchor label at the top of the page allows for the page to be
referenced by other pages. For example for the FAQ page this would be:

.. code-block:: rst

    .. _faq:

    FAQ
    ***

When the reference is used in a document, the displayed text will be that of
the next heading immediately following the label (so, FAQ in this example),
unless specifically overridden.

If you use labels within a page to refer, for example, to a subsection, use a
label that follows the format: ``[pagelabel]-[Section]`` e.g., for this
"Anchor labels" section, something like ``_docs-Anchor:`` or ``_docs-Label:``.
Using a consistent style will aid greatly when referencing from other pages.

Links
-----

To aid in documentation maintenance and keeping links up-to-date, links should
be presented in a single block at the end of the page.

Where possible, use contextual text in your links to aid users with screen
readers and other accessibility tools. For example, "check out our
:ref:`documentation style guide<docs>`" is preferable to "click
:ref:`here<docs>` for more".

Code blocks
-----------

Our documentation uses the Sphinx extension "sphinx-copybutton", which creates
a small button on the right-hand side of code blocks for users to copy the
code snippets we provide.

The copied code will strip out the prompt symbol (``$``) so that users can
paste commands directly into their terminal. For user convenience, please
ensure that code output is presented in a separate code block to the commands.

Vertical whitespace
-------------------

One newline between each section helps ensure readability of the documentation
source code.

Common words
------------

There are some common words that should follow specific usage:

- ``cloud-init``: Always hyphenated. Follows sentence case, so only
  capitalised at the start of a sentence (e.g., ``Cloud-init``).
- ``metadata``, ``datasource``: One word.
- ``user data``, ``vendor data``: Two words, not to be combined or hyphenated.

Acronyms
--------

Acronyms are always capitalised (e.g., JSON, YAML, QEMU, LXD) in text.

The first time an acronym is used on a page, it is best practice to introduce
it by showing the expanded name followed by the acronym in parentheses. E.g.,
Quick EMUlator (QEMU). If the acronym is very common, or you provide a link to
a documentation page that provides such details, you will not need to do this.


.. _Read the Docs: https://readthedocs.com/
