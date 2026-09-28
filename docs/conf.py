# pylint: disable=all

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information
import os
import datetime
import re

project = "Scenario Execution"
copyright = f"{datetime.datetime.now()}, Intel"
author = "Intel"

# The version is package.xml's, like everything else that carries one.
with open(os.path.join(os.path.dirname(__file__), "..", "scenario_execution", "package.xml"), encoding="utf-8") as _f:
    release = re.search(r"<version>\s*([^<\s]+)\s*</version>", _f.read()).group(1)
version = release

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ['sphinx.ext.extlinks',
              'sphinxcontrib.spelling']

extlinks = {'repo_link': ('https://github.com/cps-test-lab/scenario-execution/blob/main/%s', '%s')}

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

language = 'english'

linkcheck_ignore = [
    r'https://github.com/cps-test-lab/scenario-execution/.*',
]

spelling_word_list_filename = 'dictionary.txt'
spelling_ignore_contributor_names = False

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_static_path = ['.']

html_css_files = [
    'custom.css',
]

# https://docs.github.com/en/actions/learn-github-actions/contexts#github-context
github_user, github_repo = os.environ["GITHUB_REPOSITORY"].split("/", maxsplit=1)
html_context = {
    'display_github': True,
    'github_user': github_user,
    'github_repo': github_repo,
    'github_version': os.environ["GITHUB_REF_NAME"] + '/docs/',
}
