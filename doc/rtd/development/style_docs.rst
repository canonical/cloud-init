Documentation style guide
*************************

Language
--------

Where possible, text should be written in UK English. However, discretion and
common sense can both be applied. For example, where text refers to code
elements that exist in US English, the spelling of these elements should not
be changed to UK English.

Try to be concise and to the point in your writing. It is acceptable to link
to official documentation elsewhere rather than repeating content. It's also
good practice not to assume that your reader has the same level of knowledge
as you, so if you're covering a new or complicated topic, then providing
contextual links to help the reader is encouraged.

Feel free to include a "Further reading" section at the end of a page if you
have additional resources an interested reader might find helpful.

Headings
--------

In reStructuredText, headings are denoted using symbols to underline the text.
The headings used across the documentation use the following hierarchy, which
is borrowed from the `Python style guide`_:

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

Blank spaces at the ends of lines must also be removed, otherwise the `tox`
build checks will fail (it will warn you about trailing whitespace).

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

Images
------

It is generally best to avoid screenshots where possible. If you need to refer
to text output, you can use code blocks. For diagrams, we recommend the use of
`Mermaid`_.

Code blocks
-----------

Our documentation uses the Sphinx extension ``sphinx-copybutton``, which
creates a small button on the right-hand side of code blocks for users to copy
the code snippets we provide.

The copied code will strip out the prompt symbol (``$``) so that users can
paste commands directly into their terminal. For user convenience, please
ensure that code output is presented in a separate code block to the commands.

Vertical whitespace
-------------------

One newline between each section helps ensure readability of the documentation
source code.

Common words
------------

There are some common words that should follow specific usage in text:

- **cloud-init**: Always hyphenated, and follows sentence case, so only
  capitalised at the start of a sentence.
- **metadata**, **datasource**: One word.
- **user data**, **vendor data**: Two words, not to be combined or hyphenated.

When referring to file names, which may be hyphenated, they should be decorated
with backticks to ensure monospace font is used to distinguish them from
regular text.

Acronyms
--------

Acronyms are always capitalised (e.g., JSON, YAML, QEMU, LXD) in text.

The first time an acronym is used on a page, it is best practice to introduce
it by showing the expanded name followed by the acronym in parentheses. E.g.,
Quick EMUlator (QEMU). If the acronym is very common, or you provide a link to
a documentation page that provides such details, you will not need to do this.

.. _Read the Docs: https://readthedocs.com/
.. _Python style guide: https://devguide.python.org/documentation/markup/
.. _Mermaid: https://mermaid.js.org/
