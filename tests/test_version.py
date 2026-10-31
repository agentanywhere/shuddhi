"""One version, stated once. Receipts carry it, so a drift between the
package metadata and what manifests record is a receipts bug."""

import pathlib
import re

import shuddhi
from shuddhi import cli

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_pyproject_and_package_agree():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    declared = re.search(r'(?m)^version = "([^"]+)"', text).group(1)
    assert declared == shuddhi.__version__


def test_receipts_record_the_package_version():
    assert cli.FACTORY_VERSION == shuddhi.__version__
    assert cli._env_info()["factory_version"] == shuddhi.__version__


def test_version_is_pep440_release_or_dev():
    assert re.fullmatch(r"\d+\.\d+\.\d+(\.dev\d+)?", shuddhi.__version__)


def test_changelog_leads_with_this_version():
    """Unreleased code documents itself under 'Unreleased'; a released version
    must have its own dated section at the top."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    first = re.search(r"(?m)^## (.+)$", text).group(1)
    if ".dev" in shuddhi.__version__:
        assert first.startswith("Unreleased")
    else:
        assert first.startswith(shuddhi.__version__ + " ")
