import os
import sys

from cloudinit import version

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
sys.path.insert(0, os.path.abspath("../../"))
sys.path.insert(0, os.path.abspath("../"))
sys.path.insert(0, os.path.abspath("./"))
sys.path.insert(0, os.path.abspath("."))


# Suppress warnings for docs that aren't used yet
# unused_docs = [
# ]

# General information about the project.
project = "cloud-init"
copyright = "Canonical Ltd."

# -- General configuration ----------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
needs_sphinx = "4.0"

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom ones.
extensions = [
    "m2r2",
    "notfound.extension",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.viewcode",
]

# The suffix of source filenames.
source_suffix = ".rst"

# The master toctree document.
master_doc = "index"

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
version = version.version_string()
release = version

# Set the default Pygments syntax
highlight_language = "yaml"

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = []

# If true, sectionauthor and moduleauthor directives will be shown in the
# output. They are ignored by default.
show_authors = False

# Sphinx-copybutton config options: 1) prompt to be stripped from copied code.
# 2) Set to copy all lines (not just prompt lines) to ensure multiline snippets
# can be copied even if they don't contain an EOF line.
copybutton_prompt_text = "$ "
copybutton_only_copy_prompt_lines = False

# -- Options for HTML output --------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
html_theme = "furo"

# The name of an image file (relative to this directory) to place at the top
# of the sidebar.
html_static_path = ["static"]
html_theme_options = {
    "light_logo": "logo.png",
    "dark_logo": "logo-dark-mode.png",
}

# Make sure the target is unique
autosectionlabel_prefix_document = True
autosectionlabel_maxdepth = 2

# Sphinx-copybutton config options:
notfound_urls_prefix = '/'
notfound_context = {
    "title": "Page not found",
    "body": "<h1>Page not found</h1><p>Sorry we missed you! Our docs have had a remodel and some deprecated links have changed.</p><p>We are also now hosted at: <a href='https://canonical-cloud-init.readthedocs-hosted.com'>https://canonical-cloud-init.readthedocs-hosted.com</a></p>"
}
