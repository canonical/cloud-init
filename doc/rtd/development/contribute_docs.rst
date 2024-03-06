.. _docs:

Contribute to our docs
**********************

.. toctree::
    :maxdepth: 1
    :hidden:

    Style guide <style_docs.rst>
    Directory layout <docs_layout.rst>

The documentation for cloud-init is hosted in the
`cloud-init GitHub repository`_ and rendered on `Read the Docs`_. It is mostly
written in reStructuredText.

The process for contributing to the docs is largely the same as for code,
except that for cosmetic changes to the documentation (spelling, grammar, etc)
you can also use the GitHub web interface to submit changes as quick PRs.

Previewing the docs
===================

The documentation for submitted/active PRs is automatically built by Read the
Docs and served from the PR's "conversation" tab as an automatic check.

However, while you are working on docs for a feature you are adding, you will
most likely want to build the docs locally. There is a Makefile target to build
the documentation for you:

.. code-block:: shell-session

    $ tox -e doc

This will do two things:

- Build the documentation using Sphinx.
- Run doc8 against the documentation source code.

Once built, the HTML files will be viewable in `doc/rtd_html`. Use your
web browser to open `index.html` to view and navigate the site.

How are the docs structured?
============================

We use `Diataxis`_ to organise our documentation. There is more detail on the
layout of the ``doc`` directory in the :doc:`docs_layout` article.

We also have a :doc:`style_docs` that will help you if you need to edit or
write any content.

In your first PR
=================

You will need to add your GitHub username (alphabetically) to the in-repository
list that we use to track :ref:`CLA signatures <contributing-prerequisites>`:
`tools/.github-cla-signers`_.

Please include this in the same PR alongside your first contribution. Do
not create a separate PR to add your name to the CLA signatures.

If you need some help with your contribution, you can contact us on our
`IRC channel <IRC_>`_. If you have already submitted a work-in-progress PR, you
can also ask for guidance from our technical author by `tagging s-makin`_ as a
reviewer.

.. LINKS
.. include:: ../links.txt
.. _cloud-init GitHub repository: https://github.com/canonical/cloud-init/tree/main/doc/rtd
.. _Read the Docs: https://readthedocs.com/
.. _tools/.github-cla-signers: https://github.com/canonical/cloud-init/blob/main/tools/.github-cla-signers
.. _tagging s-makin: https://github.com/s-makin
