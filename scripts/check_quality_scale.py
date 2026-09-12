"""Enforce ``quality_scale.yaml``, because nothing upstream will (§9.2).

hassfest returns early for a custom integration and never parses the file, and
no reviewer grades it. So the file is a checklist we hold ourselves to, and
this script makes a tick in it mean something. A rule marked ``done`` points
at evidence that exists. Deleting that evidence breaks the build until the
yaml is updated.

It fails when:

- a rule key is missing or unknown
- a ``done`` or ``exempt`` entry has no comment
- a ``done`` comment does not start with a repo-relative path that exists
- the manifest carries a ``quality_scale`` key
- any rule is still ``todo`` and the version under check is 1.0.0 or later

The version under check is the manifest's, which the release gate holds equal
to the tag. Below 1.0.0 it reports the ``todo`` count and passes.

The rule list is copied in here with the core commit it was read from. The
yaml is parsed with the loader hassfest itself uses. That loader is Home
Assistant's, so this runs from ``scripts/check.sh``'s test stage.
"""

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

from awesomeversion import AwesomeVersion, AwesomeVersionException
from check_layout import json_document
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.yaml import load_yaml_dict

REPO_ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = Path("custom_components") / "heatit_wifi_panel"
QUALITY_SCALE = INTEGRATION / "quality_scale.yaml"
MANIFEST = INTEGRATION / "manifest.json"

#: The commit of ``home-assistant/core`` whose ``script/hassfest/quality_scale.py``
#: the list below was read from. When core adds a rule, both move together and
#: the yaml gains a ``todo``.
CORE_COMMIT = "5ffb0d10d53194d158b9f8e4361dc2200cd1ed76"

#: hassfest's ``ALL_RULES``, in its order: bronze, silver, gold, platinum.
RULES: tuple[str, ...] = (
    # bronze
    "action-setup",
    "appropriate-polling",
    "brands",
    "common-modules",
    "config-flow",
    "config-flow-test-coverage",
    "dependency-transparency",
    "docs-actions",
    "docs-conditions",
    "docs-high-level-description",
    "docs-installation-instructions",
    "docs-removal-instructions",
    "docs-triggers",
    "entity-event-setup",
    "entity-unique-id",
    "has-entity-name",
    "runtime-data",
    "test-before-configure",
    "test-before-setup",
    "unique-config-entry",
    # silver
    "action-exceptions",
    "config-entry-unloading",
    "docs-configuration-parameters",
    "docs-installation-parameters",
    "entity-unavailable",
    "integration-owner",
    "log-when-unavailable",
    "parallel-updates",
    "reauthentication-flow",
    "test-coverage",
    # gold
    "devices",
    "diagnostics",
    "discovery",
    "discovery-update-info",
    "docs-data-update",
    "docs-examples",
    "docs-known-limitations",
    "docs-supported-devices",
    "docs-supported-functions",
    "docs-troubleshooting",
    "docs-use-cases",
    "dynamic-devices",
    "entity-category",
    "entity-device-class",
    "entity-disabled-by-default",
    "entity-translations",
    "exception-translations",
    "icon-translations",
    "reconfiguration-flow",
    "repair-issues",
    "stale-devices",
    # platinum
    "async-dependency",
    "inject-websession",
    "strict-typing",
)

STATUSES = frozenset({"done", "todo", "exempt"})
#: hassfest's schema for the mapping form: these two keys and no other.
ENTRY_KEYS = frozenset({"status", "comment"})
#: The first release that may carry no ``todo`` (§9.2, failure condition 5).
FIRST_COMPLETE_VERSION = AwesomeVersion("1.0.0")
#: Punctuation a comment may attach to a path before its prose.
TRAILING_PUNCTUATION = ".,:;"
#: A word starting with one of these is a repo path wherever it sits in the
#: comment, and must exist like the first word. A comment that names a second
#: module as evidence is held to it.
TREE_PREFIXES = ("custom_components/", "scripts/", "tests/", "docs/")


@dataclass
class QualityScaleCheck:
    """What the gate found: the problems, and the rules still ``todo``."""

    problems: list[str] = field(default_factory=list)
    todo: list[str] = field(default_factory=list)


class Entry(NamedTuple):
    """One rule's value, read out of either of hassfest's two shapes."""

    status: str
    comment: str | None


class MalformedRuleError(ValueError):
    """A rule's value is in neither of hassfest's shapes; the message says why."""


def load_rules(root: Path) -> tuple[dict[str, Any], list[str]]:
    """Return the ``rules`` mapping, or the one problem that stops the gate."""
    path = root / QUALITY_SCALE
    if not path.is_file():
        return {}, [f"{QUALITY_SCALE}: missing"]
    try:
        document = load_yaml_dict(path)
    except HomeAssistantError as err:
        return {}, [f"{QUALITY_SCALE}: {err}"]
    if set(document) != {"rules"} or not isinstance(document["rules"], dict):
        problem = (
            f"{QUALITY_SCALE}: the document is a 'rules' mapping and nothing "
            f"else, but its keys are {sorted(document)}"
        )
        return {}, [problem]
    return document["rules"], []


def read_entry(rule: str, value: object) -> Entry:
    """Read one rule's value, or raise :class:`MalformedRuleError` with the reason.

    hassfest's two shapes: a bare string is a status with no comment, and a
    mapping carries ``status`` and ``comment`` and nothing else.
    """
    if isinstance(value, str):
        status, comment = value, None
    elif isinstance(value, dict):
        if set(value) != ENTRY_KEYS:
            msg = (
                f"{QUALITY_SCALE}: {rule} carries {sorted(value)}, must be "
                f"exactly {sorted(ENTRY_KEYS)}"
            )
            raise MalformedRuleError(msg)
        status = value["status"]
        comment = value["comment"] if isinstance(value["comment"], str) else None
    else:
        msg = f"{QUALITY_SCALE}: {rule} is {value!r}, not a rule"
        raise MalformedRuleError(msg)
    if status not in STATUSES:
        msg = (
            f"{QUALITY_SCALE}: {rule} is {status!r}, must be one of {sorted(STATUSES)}"
        )
        raise MalformedRuleError(msg)
    return Entry(status, comment or None)


def evidence_problems(root: Path, rule: str, comment: str) -> list[str]:
    """Return why a ``done`` comment's paths are not evidence, one line each.

    The first whitespace-delimited word must be a path inside ``root`` that
    exists. So must any later word that starts like one. Punctuation the prose
    attached to either is removed first.
    """
    first, *rest = (word.rstrip(TRAILING_PUNCTUATION) for word in comment.split())
    named = [first, *(word for word in rest if word.startswith(TREE_PREFIXES))]
    problems = []
    for word in named:
        candidate = Path(word)
        if candidate.is_absolute() or ".." in candidate.parts:
            problems.append(
                f"{QUALITY_SCALE}: {rule} is done, but {word!r} is not a "
                f"repo-relative path"
            )
        elif not (root / candidate).exists():
            problems.append(
                f"{QUALITY_SCALE}: {rule} is done, but its evidence {word!r} does "
                f"not exist. A done comment starts with the test, module or "
                f"directory that proves it"
            )
    return problems


def check_rules(root: Path, rules: dict[str, Any]) -> QualityScaleCheck:
    """Apply failure conditions 1 to 3 over the mapping, collecting the ``todo``."""
    result = QualityScaleCheck()
    result.problems.extend(
        f"{QUALITY_SCALE}: {rule} is missing" for rule in RULES if rule not in rules
    )
    result.problems.extend(
        f"{QUALITY_SCALE}: {rule} is unknown. The copied list is core's at "
        f"{CORE_COMMIT[:12]}"
        for rule in rules
        if rule not in RULES
    )
    for rule in RULES:
        if rule not in rules:
            continue
        try:
            entry = read_entry(rule, rules[rule])
        except MalformedRuleError as err:
            result.problems.append(str(err))
            continue
        if entry.status == "todo":
            result.todo.append(rule)
        elif entry.comment is None:
            result.problems.append(
                f"{QUALITY_SCALE}: {rule} is {entry.status} and has no comment"
            )
        elif entry.status == "done":
            result.problems.extend(evidence_problems(root, rule, entry.comment))
    return result


def check_manifest(root: Path) -> tuple[list[str], str | None]:
    """Check that the manifest makes no claim, and return the version under check."""
    manifest = json_document(root / MANIFEST)
    if manifest is None:
        return [f"{MANIFEST}: missing"], None
    problems = []
    if "quality_scale" in manifest:
        problems.append(
            f"{MANIFEST}: no quality_scale key. The yaml says what we hold "
            f"ourselves to, and the manifest makes no claim a reviewer never graded"
        )
    version = manifest.get("version")
    return problems, version if isinstance(version, str) else None


def check_todo(todo: list[str], version: str | None) -> list[str]:
    """Failure condition 5: from 1.0.0 on, nothing is still ``todo``."""
    if not todo or version is None:
        return []
    try:
        complete = AwesomeVersion(version) >= FIRST_COMPLETE_VERSION
    except AwesomeVersionException:
        return [
            f"{MANIFEST}: version {version!r} does not parse, so nothing can be todo"
        ]
    if not complete:
        return []
    return [
        f"{QUALITY_SCALE}: {rule} is todo, and {version} is {FIRST_COMPLETE_VERSION} "
        f"or later. Mark it done, or exempt with a reason"
        for rule in todo
    ]


def check_quality_scale(root: Path) -> QualityScaleCheck:
    """Run the whole gate over the tree at ``root``."""
    rules, problems = load_rules(root)
    if problems:
        return QualityScaleCheck(problems=problems)
    result = check_rules(root, rules)
    manifest_problems, version = check_manifest(root)
    result.problems.extend(manifest_problems)
    result.problems.extend(check_todo(result.todo, version))
    return result


def main(argv: list[str] | None = None) -> None:
    """Parse the command line, run the gate and report."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        metavar="DIR",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    result = check_quality_scale(args.root)
    if result.problems:
        sys.exit(
            "\n".join(f"check_quality_scale: {problem}" for problem in result.problems)
        )
    if result.todo:
        print(  # noqa: T201  # the report is the script's output
            f"check_quality_scale: {len(result.todo)} rules todo: "
            + ", ".join(result.todo)
        )


if __name__ == "__main__":
    main()
