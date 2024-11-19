import datetime
import glob
import itertools
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
    "sphinxcontrib.mermaid",
    "sphinxcontrib.spelling",
]


# Spelling settings for sphinxcontrib.spelling
# https://docs.ubuntu.com/styleguide/en/
spelling_warning = True

templates_path = ["templates"]
# Uses case-independent spelling matches from doc/rtd/spelling_word_list.txt
spelling_filters = ["spelling.WordListFilter"]
spelling_word_list_filename = "spelling_word_list.txt"

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
html_js_files = [
    "js/github_issue_links.js",
    "js/mermaid_config.js",
    "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js",
]

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


def get_changed_str(prop_name, prop_cfg):
    changed_cfg = {}
    if prop_cfg.get("changed"):
        changed_cfg = prop_cfg
    for oneof_cfg in prop_cfg.get("oneOf", []):
        if oneof_cfg.get("changed"):
            changed_cfg = oneof_cfg
            break
    if changed_cfg:
        with open("templates/property_changed.tmpl", "r") as stream:
            content = "## template: jinja\n" + stream.read()
        return render_jinja_payload(
            content, f"changed_{prop_name}", changed_cfg
        )
    return ""


def get_deprecated_str(prop_name, prop_cfg):
    deprecated_cfg = {}
    if prop_cfg.get("deprecated"):
        deprecated_cfg = prop_cfg
    for oneof_cfg in prop_cfg.get("oneOf", []):
        if oneof_cfg.get("deprecated"):
            deprecated_cfg = oneof_cfg
            break
    if deprecated_cfg:
        with open("templates/property_deprecation.tmpl", "r") as stream:
            content = "## template: jinja\n" + stream.read()
        return render_jinja_payload(
            content, f"deprecation_{prop_name}", deprecated_cfg
        )
    return ""


def render_property_template(prop_name, prop_cfg, prefix=""):
    if prop_cfg.get("description"):
        description = f" {prop_cfg['description']}"
    else:
        description = ""
    description += get_deprecated_str(prop_name, prop_cfg)
    description += get_changed_str(prop_name, prop_cfg)
    jinja_vars = {
        "prefix": prefix,
        "name": prop_name,
        "description": description,
        "types": get_types_str(prop_cfg),
        "prop_cfg": prop_cfg,
    }
    with open("templates/module_property.tmpl", "r") as stream:
        content = "## template: jinja\n" + stream.read()
    return render_jinja_payload(content, f"doc_module_{prop_name}", jinja_vars)


def flatten_schema_refs(src_cfg: dict, defs: dict):
    """Flatten schema: replace $refs in src_cfg with definitions from $defs."""
    if "$ref" in src_cfg:
        reference = src_cfg.pop("$ref").replace("#/$defs/", "")
        # Update the defined references in subschema for doc rendering
        src_cfg.update(defs[reference])
    if "items" in src_cfg:
        if "$ref" in src_cfg["items"]:
            reference = src_cfg["items"].pop("$ref").replace("#/$defs/", "")
            # Update the references in subschema for doc rendering
            src_cfg["items"].update(defs[reference])
        if "oneOf" in src_cfg["items"]:
            for sub_schema in src_cfg["items"]["oneOf"]:
                if "$ref" in sub_schema:
                    reference = sub_schema.pop("$ref").replace("#/$defs/", "")
                    sub_schema.update(defs[reference])
    for sub_schema in itertools.chain(
        src_cfg.get("oneOf", []),
        src_cfg.get("anyOf", []),
        src_cfg.get("allOf", []),
    ):
        if "$ref" in sub_schema:
            reference = sub_schema.pop("$ref").replace("#/$defs/", "")
            sub_schema.update(defs[reference])


def flatten_schema_all_of(src_cfg: dict):
    """Flatten schema: Merge allOf.

    If a schema as allOf, then all of the sub-schemas must hold. Therefore
    it is safe to merge them.
    """
    sub_schemas = src_cfg.pop("allOf", None)
    if not sub_schemas:
        return
    for sub_schema in sub_schemas:
        src_cfg.update(sub_schema)


def render_nested_properties(prop_cfg, defs, prefix):
    prop_str = ""
    prop_types = set(["properties", "patternProperties"])
    flatten_schema_refs(prop_cfg, defs)
    if "items" in prop_cfg:
        prop_str += render_nested_properties(prop_cfg["items"], defs, prefix)
        for alt_schema in prop_cfg["items"].get("oneOf", []):
            if prop_types.intersection(alt_schema):
                prop_str += render_nested_properties(alt_schema, defs, prefix)

    for hidden_key in prop_cfg.get("hidden", []):
        prop_cfg.pop(hidden_key, None)

    # Render visible property types
    for prop_type in prop_types.intersection(prop_cfg):
        for prop_name, nested_cfg in prop_cfg.get(prop_type, {}).items():
            flatten_schema_all_of(nested_cfg)
            flatten_schema_refs(nested_cfg, defs)
            if nested_cfg.get("label"):
                prop_name = nested_cfg.get("label")
            prop_str += render_property_template(prop_name, nested_cfg, prefix)
            prop_str += render_nested_properties(
                nested_cfg, defs, prefix + "  "
            )
    return prop_str


def debug_module_docs(
    module_id: str, mod_docs: dict, debug_file_path: str = None
):
    """Print rendered RST module docs during build.

    The intent is to make rendered RST inconsistencies easier to see when
    modifying jinja template files or JSON schema as white-space and format
    inconsistencies can lead to significant sphinx rendering issues in RTD.

    To trigger this inline print of rendered docs, set the environment
    variable CLOUD_INIT_DEBUG_MODULE_DOC.

    :param module_id: A specific 'cc_*' module name to print rendered RST for,
        or provide 'all' to print out all rendered module docs.
    :param mod_docs: A dict represnting doc metadata for each config module.
        The dict is keyed on config module id (cc_*) and each value is a dict
        with values such as: title, name, examples, schema_doc.
    :param debug_file_path: A specific file to write the rendered RST content.
        When unset,
    """
    from cloudinit.util import load_text_file, load_yaml

    if not module_id:
        return
    if module_id == "all":
        module_ids = mod_docs.keys()
    else:
        module_ids = [module_id]
    rendered_content = ""
    for mod_id in module_ids:
        try:
            data = load_yaml(
                load_text_file(f"../module-docs/{mod_id}/data.yaml")
            )
        except FileNotFoundError:
            continue
        with open("templates/modules.tmpl", "r") as stream:
            tmpl_content = "## template: jinja\n" + stream.read()
            params = {"data": data, "config": {"html_context": mod_docs}}
            rendered_content += render_jinja_payload(
                tmpl_content, "changed_modules_page", params
            )
    if debug_file_path:
        print(f"--- Writing rendered module docs: {debug_file_path} ---")
        with open(debug_file_path, "w") as stream:
            stream.write(rendered_content)
    else:
        print(rendered_content)


def render_module_schemas():
    from cloudinit.importer import import_module

    mod_docs = {}
    schema = get_schema()
    defs = schema.get("$defs", {})

    for mod_path in glob.glob("../../cloudinit/config/cc_*py"):
        mod_name = os.path.basename(mod_path).replace(".py", "")
        mod = import_module(f"cloudinit.config.{mod_name}")
        cc_key = mod.meta["id"]
        mod_docs[cc_key] = {
            "meta": mod.meta,
        }
        if cc_key in defs:
            mod_docs[cc_key]["schema_doc"] = render_nested_properties(
                defs[cc_key], defs, ""
            )
        else:
            mod_docs[cc_key][
                "schema_doc"
            ] = "No schema definitions for this module"
    debug_module_docs(
        os.environ.get("CLOUD_INIT_DEBUG_MODULE_DOC"),
        mod_docs,
        debug_file_path=os.environ.get("CLOUD_INIT_DEBUG_MODULE_DOC_FILE"),
    )
    return mod_docs


html_context = render_module_schemas()
