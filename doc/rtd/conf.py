import datetime
import os
import sys

from cloudinit import version
from cloudinit.config.schema import get_schema
from cloudinit.handlers.jinja_template import render_jinja_payload

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
    "sphinxcontrib.datatemplates",
    "sphinxcontrib.spelling",
]


# Spelling settings for sphinxcontrib.spelling
# https://docs.ubuntu.com/styleguide/en/
spelling_warning = True

templates_path = ["templates"]
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
copybutton_prompt_text = r"\$ |PS> "
copybutton_prompt_is_regexp = True
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
    r"https://www.scaleway.com/en/developers/api/instance.*",
    r"https://powersj.io.*",
    r"http://169.254.169.254.*",
    r"http://10.10.0.1.*",
]

linkcheck_anchors_ignore_for_url = (
    # Ignore github anchors in rst or md files
    r"https://github.com/.*\.rst",
    r"https://github.com/.*\.md",
    # Ignore github line number anchors in cloud-init and ubuntu-pro-client
    r"https://github.com/canonical/cloud-init.*",
    r"https://github.com/canonical/ubuntu-pro-client.*",
)

new_doc_issue_link = (
    "https://github.com/canonical/cloud-init/issues/new?"
    "labels=documentation%2C+new&projects=&template=documentation.md&"
    "title=%5Bdocs%5D%3A+missing+redirect"
)
docs_url = "https://docs.cloud-init.io"

# Sphinx-copybutton config options:
notfound_body = (
    "<h1>Page not found</h1><p>Sorry we missed you! Our docs have had a"
    " remodel and some deprecated links have changed. Please"
    f" <a href='{new_doc_issue_link}'>file a documentation bug</a> and"
    " we'll fix this redirect.</p><p>"
    f"<a href='{docs_url}'>Back to our homepage hosted at {docs_url}</a></p>"
)

notfound_context = {
    "title": "Page not found",
    "body": notfound_body,
}


def get_types_str(prop_cfg):
    """Return formatted string for all supported config types."""
    types = ""

    # When oneOf present, join each alternative with an '/'
    types += "/".join(
        get_types_str(oneof_cfg) for oneof_cfg in prop_cfg.get("oneOf", [])
    )
    if "items" in prop_cfg:
        types = f"{prop_cfg['type']} of "
        types += get_types_str(prop_cfg["items"])
    elif "enum" in prop_cfg:
        types += f"{'/'.join([f'``{enum}``' for enum in prop_cfg['enum']])}"
    elif "type" in prop_cfg:
        if isinstance(prop_cfg["type"], list):
            types = "/".join(prop_cfg["type"])
        else:
            types = prop_cfg["type"]
    return types


def render_property_template(prop_name, prop_cfg, prefix=""):
    with open("templates/module_property.tmpl", "r") as stream:
        content = "## template: jinja\n" + stream.read()
    if prop_cfg.get("description"):
        description = f" {prop_cfg['description']}"
    else:
        description = ""
    jinja_vars = {
        "prefix": prefix,
        "name": prop_name,
        "description": description,
        "types": get_types_str(prop_cfg),
        "prop_cfg": prop_cfg,
    }
    return render_jinja_payload(content, f"doc_module_{prop_name}", jinja_vars)


def render_nested_properties(prop_cfg, prefix):
    prop_str = ""
    if "items" in prop_cfg:
        prop_str += render_nested_properties(prop_cfg["items"], prefix)
    if "properties" not in prop_cfg:
        return prop_str
    for prop_name, nested_cfg in prop_cfg["properties"].items():
        prop_str += render_property_template(prop_name, nested_cfg, prefix)
        prop_str += render_nested_properties(nested_cfg, prefix + "  ")
    return prop_str


def render_module_schemas():
    from cloudinit.importer import find_module, import_module

    mod_docs = {}
    schema = get_schema()
    for key in schema["$defs"]:
        if key[:3] != "cc_":
            continue
        locs, _ = find_module(key, ["", "cloudinit.config"], ["meta"])
        mod = import_module(locs[0])
        mod_docs[key] = {
            "schema_doc": render_nested_properties(schema["$defs"][key], ""),
            "meta": mod.meta,
        }
    return mod_docs


html_context = render_module_schemas()
