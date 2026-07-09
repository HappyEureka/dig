"""Sphinx configuration for the dig docs.

Renders the Markdown guides (via MyST) and builds an API reference straight from
the code's docstrings (autodoc); `viewcode` adds a [source] link by each object.
Build from the repo root:

    ./scripts/build_docs.sh
"""

import os
import sys

# make the `dig` package importable for autodoc (docs/ -> repo root)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

project = "dig"
author = "dig contributors"

extensions = [
    "myst_parser",            # read Markdown
    "sphinx.ext.autodoc",     # pull signatures + docstrings from the code
    "sphinx.ext.napoleon",    # google/numpy-style docstrings
    "sphinx.ext.viewcode",    # link to highlighted source
]

myst_enable_extensions = ["colon_fence", "deflist"]

autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_class_signature = "separated"

root_doc = "index"
source_suffix = {".md": "markdown"}

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "furo"
html_title = "dig"
html_theme_options = {
    # recolor here -- change these hex values to retheme (indigo by default)
    "light_css_variables": {
        "color-brand-primary": "#3f51b5",
        "color-brand-content": "#3f51b5",
    },
    "dark_css_variables": {
        "color-brand-primary": "#9fa8da",
        "color-brand-content": "#9fa8da",
    },
}
