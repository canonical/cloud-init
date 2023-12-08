import datetime
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
copyright = f"Canonical Group Ltd, {datetime.date.today().year}"

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
    "sphinxcontrib.spelling",
]


# Spelling settings for sphinxcontrib.spelling
# https://docs.ubuntu.com/styleguide/en/
spelling_warning = True

# Uses case-independent spelling matches from doc/rtd/spelling_word_list.txt
spelling_filters = ["spelling.WordListFilter"]

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
html_theme_options = {
    "light_logo": "logo.png",
    "dark_logo": "logo-dark-mode.png",
    "light_css_variables": {
        "font-stack": "Ubuntu, -apple-system, Segoe UI, Roboto, Oxygen, Cantarell, Fira Sans, Droid Sans, Helvetica Neue, sans-serif",  # noqa: E501
        "font-stack--monospace": "Ubuntu Mono variable, Ubuntu Mono, Consolas, Monaco, Courier, monospace",  # noqa: E501
        "color-foreground-primary": "#111",
        "color-foreground-secondary": "var(--color-foreground-primary)",
        "color-foreground-muted": "#333",
        "color-background-secondary": "#FFF",
        "color-background-hover": "#f2f2f2",
        "color-brand-primary": "#111",
        "color-brand-content": "#06C",
        "color-inline-code-background": "rgba(0,0,0,.03)",
        "color-sidebar-link-text": "#111",
        "color-sidebar-item-background--current": "#ebebeb",
        "color-sidebar-item-background--hover": "#f2f2f2",
        "sidebar-item-line-height": "1.3rem",
        "color-link-underline": "var(--color-background-primary)",
        "color-link-underline--hover": "var(--color-background-primary)",
    },
    "dark_css_variables": {
        "color-foreground-secondary": "var(--color-foreground-primary)",
        "color-foreground-muted": "#CDCDCD",
        "color-background-secondary": "var(--color-background-primary)",
        "color-background-hover": "#666",
        "color-brand-primary": "#fff",
        "color-brand-content": "#06C",
        "color-sidebar-link-text": "#f7f7f7",
        "color-sidebar-item-background--current": "#666",
        "color-sidebar-item-background--hover": "#333",
    },
}

# The name of an image file (relative to this directory) to place at the top
# of the sidebar.
html_static_path = ["static"]
html_css_files = ["css/custom.css", "css/github_issue_links.css"]
html_js_files = ["js/github_issue_links.js"]

html_extra_path = ["googleaf254801a5285c31.html"]

# Make sure the target is unique
autosectionlabel_prefix_document = True
autosectionlabel_maxdepth = 2

# Sphinx-linkcheck config
linkcheck_ignore = [
    r"http://\[fd00:ec2::254.*",
    r"http://instance-data.*",
    r"https://powersj.io.*",
    r"http://169.254.169.254.*",
    r"http://10.10.0.1.*",
]

linkcheck_anchors_ignore_for_url = (
    r"https://github.com/canonical/cloud-init.*",
    r"https://github.com/canonical/ubuntu-pro-client.*",
)

# Sphinx-copybutton config options:
notfound_body = (
    "<h1>Page not found</h1><p>Sorry we missed you! Our docs have had a"
    " remodel and some deprecated links have changed.</p><p>"
    "<a href='https://canonical-cloud-init.readthedocs-hosted.com'>Back to our"
    " homepage now hosted at"
    " https://canonical-cloud-init.readthedocs-hosted.com</a></p>"
)
notfound_context = {
    "title": "Page not found",
    "body": notfound_body,
}
