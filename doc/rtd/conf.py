import os
import sys

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
sys.path.insert(0, os.path.abspath('../../'))
sys.path.insert(0, os.path.abspath('../'))
sys.path.insert(0, os.path.abspath('./'))
sys.path.insert(0, os.path.abspath('.'))

from cloudinit import version
from cloudinit.config.schema import get_schema_doc

# Supress warnings for docs that aren't used yet
# unused_docs = [
# ]

# General information about the project.
project = 'Cloud-Init'

# -- General configuration ----------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
# needs_sphinx = '1.0'

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom ones.
extensions = [
    'sphinx.ext.intersphinx',
    'sphinx.ext.autodoc',
    'sphinx.ext.autosectionlabel',
    'sphinx.ext.viewcode',
]

intersphinx_mapping = {
    'sphinx': ('http://sphinx.pocoo.org', None)
}

# The suffix of source filenames.
source_suffix = '.rst'

# The master toctree document.
master_doc = 'index'

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
version = version.version_string()
release = version

# Set the default Pygments syntax
highlight_language = 'yaml'

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = []

# If true, sectionauthor and moduleauthor directives will be shown in the
# output. They are ignored by default.
show_authors = False

# -- Options for HTML output --------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
html_theme = 'default'

# Theme options are theme-specific and customize the look and feel of a theme
# further.  For a list of options available for each theme, see the
# documentation.
html_theme_options = {
    "bodyfont": "Ubuntu, Arial, sans-serif",
    "headfont": "Ubuntu, Arial, sans-serif"
}

# The name of an image file (relative to this directory) to place at the top
# of the sidebar.
html_logo = 'static/logo.png'

def generate_docstring_from_schema(app, what, name, obj, options, lines):
    """Override module docs from schema when present."""
    if what == 'module' and hasattr(obj, "schema"):
        del lines[:]
        lines.extend(get_schema_doc(obj.schema).split('\n'))

def setup(app):
    app.connect('autodoc-process-docstring', generate_docstring_from_schema)
