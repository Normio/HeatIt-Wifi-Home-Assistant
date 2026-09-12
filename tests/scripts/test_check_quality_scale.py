"""The quality-scale gate: every failure mode red, the clean case green.

Each test builds a throwaway tree: the yaml, the manifest and whatever
evidence the yaml points at. It breaks one rule and asserts the script names
exactly that problem. The last test runs the gate over the real tree. That is
the check itself.
"""

import json
import re
from typing import TYPE_CHECKING

import pytest
from check_quality_scale import (
    CORE_COMMIT,
    REPO_ROOT,
    RULES,
    check_quality_scale,
    main,
)

if TYPE_CHECKING:
    from pathlib import Path

EVIDENCE = "tests/evidence.py"
"""The file every ``done`` comment in the throwaway tree points at."""

RULE_KEY = re.compile(r"^[a-z]+(-[a-z]+)*$")


def rules_yaml(*, without: str | None = None, **overrides: str) -> str:
    """Render every rule as ``done`` with evidence, then apply the overrides.

    An override is the yaml for that one rule's value, word for word, so a test
    reads as the yaml it is about. ``without`` leaves one rule out.
    """
    lines = ["rules:"]
    for rule in RULES:
        if rule == without:
            continue
        value = overrides.pop(rule, None)
        if value is None:
            lines.append(f"  {rule}:")
            lines.append("    status: done")
            lines.append(f"    comment: {EVIDENCE} asserts it")
        elif "\n" in value:
            lines.append(f"  {rule}:")
            lines.extend(f"    {line}" for line in value.splitlines())
        else:
            lines.append(f"  {rule}: {value}")
    assert not overrides, f"not rules: {sorted(overrides)}"
    return "\n".join(lines) + "\n"


def tree(
    root: Path,
    yaml: str | None,
    *,
    version: str = "0.4.0",
    manifest_extra: dict[str, object] | None = None,
) -> Path:
    """Write the yaml, the manifest and the evidence file under ``root``."""
    integration = root / "custom_components" / "heatit_wifi_panel"
    integration.mkdir(parents=True)
    if yaml is not None:
        (integration / "quality_scale.yaml").write_text(yaml, encoding="utf-8")
    manifest: dict[str, object] = {"domain": "heatit_wifi_panel", "version": version}
    manifest.update(manifest_extra or {})
    (integration / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "tests").mkdir()
    (root / EVIDENCE).write_text("", encoding="utf-8")
    return root


def problems(root: Path) -> list[str]:
    """Run the gate over ``root`` and return what it found."""
    return check_quality_scale(root).problems


# --- the copied-in rule list -------------------------------------------------


def test_the_rule_list_is_hassfests_fifty_four() -> None:
    """§9.2: all 54 hyphenated keys, copied in with the core commit."""
    assert len(RULES) == 54
    assert len(set(RULES)) == len(RULES)
    assert all(RULE_KEY.match(rule) for rule in RULES)
    assert re.fullmatch(r"[0-9a-f]{40}", CORE_COMMIT)


# --- the clean case ----------------------------------------------------------


def test_a_complete_yaml_with_evidence_passes(tmp_path: Path) -> None:
    root = tree(tmp_path, rules_yaml())

    result = check_quality_scale(root)

    assert result.problems == []
    assert result.todo == []


def test_the_real_tree_passes() -> None:
    """The gate itself, run over the checkout the tests are running in."""
    assert problems(REPO_ROOT) == []


# --- failure condition 1: the rule set ---------------------------------------


def test_a_missing_rule_is_named(tmp_path: Path) -> None:
    root = tree(tmp_path, rules_yaml(without="brands"))

    found = problems(root)

    assert len(found) == 1
    assert "brands" in found[0]
    assert "missing" in found[0]


def test_an_unknown_rule_is_named(tmp_path: Path) -> None:
    root = tree(tmp_path, rules_yaml() + "  docs-everything: todo\n")

    found = problems(root)

    assert len(found) == 1
    assert "docs-everything" in found[0]
    assert "unknown" in found[0]


def test_a_top_level_key_other_than_rules_is_refused(tmp_path: Path) -> None:
    """The schema is hassfest's: ``rules``, and nothing else."""
    root = tree(tmp_path, rules_yaml() + "tier: gold\n")

    found = problems(root)

    assert len(found) == 1
    assert "tier" in found[0]


@pytest.mark.parametrize("yaml", ["", "rules: []\n", "- brands\n", "rules:\n"])
def test_a_document_without_a_rules_mapping_is_refused(
    tmp_path: Path, yaml: str
) -> None:
    root = tree(tmp_path, yaml)

    found = problems(root)

    assert len(found) == 1
    assert "quality_scale.yaml" in found[0]


def test_unparseable_yaml_is_one_problem(tmp_path: Path) -> None:
    root = tree(tmp_path, "rules: [\n")

    found = problems(root)

    assert len(found) == 1


def test_a_missing_yaml_is_one_problem(tmp_path: Path) -> None:
    root = tree(tmp_path, None)

    found = problems(root)

    assert len(found) == 1
    assert "quality_scale.yaml" in found[0]
    assert "missing" in found[0]


# --- failure condition 2: comments -------------------------------------------


@pytest.mark.parametrize("value", ["done", "exempt"])
def test_a_bare_done_or_exempt_has_no_comment(tmp_path: Path, value: str) -> None:
    root = tree(tmp_path, rules_yaml(brands=value))

    found = problems(root)

    assert len(found) == 1
    assert "brands" in found[0]
    assert "no comment" in found[0]


@pytest.mark.parametrize("status", ["done", "exempt"])
@pytest.mark.parametrize("comment", ['""', "null"])
def test_an_empty_comment_is_no_comment(
    tmp_path: Path, status: str, comment: str
) -> None:
    root = tree(tmp_path, rules_yaml(brands=f"status: {status}\ncomment: {comment}"))

    found = problems(root)

    assert len(found) == 1
    assert "brands" in found[0]
    assert "no comment" in found[0]


def test_a_bare_todo_needs_none(tmp_path: Path) -> None:
    root = tree(tmp_path, rules_yaml(brands="todo"))

    assert problems(root) == []


def test_a_status_outside_the_three_is_refused(tmp_path: Path) -> None:
    root = tree(tmp_path, rules_yaml(brands="status: skipped\ncomment: x"))

    found = problems(root)

    assert len(found) == 1
    assert "brands" in found[0]
    assert "skipped" in found[0]


def test_a_mapping_carries_status_and_comment_and_nothing_else(
    tmp_path: Path,
) -> None:
    """The schema is hassfest's, exactly: an extra key is a typo it rejects."""
    root = tree(
        tmp_path,
        rules_yaml(brands=f"status: done\ncomment: {EVIDENCE}\nreason: x"),
    )

    found = problems(root)

    assert len(found) == 1
    assert "brands" in found[0]
    assert "reason" in found[0]


# --- failure condition 3: a done comment starts with evidence ----------------


def test_a_done_comment_must_start_with_a_path_that_exists(tmp_path: Path) -> None:
    root = tree(
        tmp_path,
        rules_yaml(brands="status: done\ncomment: tests/gone.py asserted it"),
    )

    found = problems(root)

    assert len(found) == 1
    assert "brands" in found[0]
    assert "tests/gone.py" in found[0]


def test_a_done_comment_that_is_only_prose_fails(tmp_path: Path) -> None:
    root = tree(tmp_path, rules_yaml(brands="status: done\ncomment: it is done"))

    found = problems(root)

    assert len(found) == 1
    assert "brands" in found[0]


@pytest.mark.parametrize(
    "comment",
    [
        EVIDENCE,
        f"{EVIDENCE} asserts it on every entity",
        f'"{EVIDENCE}: the category column"',
        f"{EVIDENCE}, and the module itself.",
        "tests",
        "tests/",
    ],
    ids=["bare", "prose after", "colon", "comma and period", "directory", "slash"],
)
def test_free_text_may_follow_the_path(tmp_path: Path, comment: str) -> None:
    root = tree(tmp_path, rules_yaml(brands=f"status: done\ncomment: {comment}"))

    assert problems(root) == []


def test_every_repo_path_the_comment_names_must_exist(tmp_path: Path) -> None:
    """A second module named as evidence must exist too, wherever it sits."""
    root = tree(
        tmp_path,
        rules_yaml(
            brands=f"status: done\ncomment: {EVIDENCE} and tests/gone.py, both",
        ),
    )

    found = problems(root)

    assert len(found) == 1
    assert "brands" in found[0]
    assert "tests/gone.py" in found[0]


def test_a_word_that_is_not_a_repo_path_is_prose(tmp_path: Path) -> None:
    root = tree(
        tmp_path,
        rules_yaml(brands=f"status: done\ncomment: {EVIDENCE} reads en.json/name"),
    )

    assert problems(root) == []


@pytest.mark.parametrize("path", ["/etc/passwd", "../tests/evidence.py"])
def test_the_path_is_repo_relative(tmp_path: Path, path: str) -> None:
    """An absolute path, or one climbing out, is not evidence in this tree."""
    tree(tmp_path / "repo", rules_yaml(brands=f"status: done\ncomment: {path} x"))
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "evidence.py").write_text("", encoding="utf-8")

    found = problems(tmp_path / "repo")

    assert len(found) == 1
    assert "brands" in found[0]


def test_an_exempt_comment_is_a_reason_not_a_path(tmp_path: Path) -> None:
    root = tree(tmp_path, rules_yaml(brands="status: exempt\ncomment: no such thing"))

    assert problems(root) == []


# --- failure condition 4: the manifest makes no claim ------------------------


def test_a_manifest_quality_scale_key_fails(tmp_path: Path) -> None:
    root = tree(tmp_path, rules_yaml(), manifest_extra={"quality_scale": "gold"})

    found = problems(root)

    assert len(found) == 1
    assert "manifest.json" in found[0]
    assert "quality_scale" in found[0]


def test_a_missing_manifest_is_one_problem(tmp_path: Path) -> None:
    root = tree(tmp_path, rules_yaml())
    (root / "custom_components" / "heatit_wifi_panel" / "manifest.json").unlink()

    found = problems(root)

    assert len(found) == 1
    assert "manifest.json" in found[0]


# --- failure condition 5: nothing is todo from 1.0.0 -------------------------


@pytest.mark.parametrize("version", ["0.4.0", "0.99.9"])
def test_a_todo_is_reported_and_passes_before_one_point_oh(
    tmp_path: Path, version: str
) -> None:
    root = tree(
        tmp_path,
        rules_yaml(brands="todo", devices="status: todo\ncomment: next release"),
        version=version,
    )

    result = check_quality_scale(root)

    assert result.problems == []
    assert result.todo == ["brands", "devices"]


@pytest.mark.parametrize("version", ["1.0.0", "1.2.3", "2.0.0"])
def test_a_todo_fails_from_one_point_oh(tmp_path: Path, version: str) -> None:
    root = tree(tmp_path, rules_yaml(brands="todo"), version=version)

    found = problems(root)

    assert len(found) == 1
    assert "brands" in found[0]
    assert version in found[0]


def test_an_unparseable_version_is_named_rather_than_raised(tmp_path: Path) -> None:
    root = tree(tmp_path, rules_yaml(brands="todo"), version="not a version")

    found = problems(root)

    assert len(found) == 1
    assert "manifest.json" in found[0]
    assert "not a version" in found[0]


def test_the_version_under_check_is_the_manifests(tmp_path: Path) -> None:
    """A 1.0.0 with no todo passes: the version alone changes nothing."""
    root = tree(tmp_path, rules_yaml(), version="1.0.0")

    assert problems(root) == []


# --- the command line --------------------------------------------------------


def test_main_is_silent_when_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tree(tmp_path, rules_yaml())

    main(["--root", str(root)])

    assert capsys.readouterr() == ("", "")


def test_main_reports_the_todo_count_and_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tree(tmp_path, rules_yaml(brands="todo", devices="todo"))

    main(["--root", str(root)])

    out, err = capsys.readouterr()
    assert err == ""
    assert out == "check_quality_scale: 2 rules todo: brands, devices\n"


def test_main_exits_non_zero_naming_every_problem(tmp_path: Path) -> None:
    """``sys.exit`` with a string: the interpreter prints it and exits 1."""
    root = tree(
        tmp_path,
        rules_yaml(brands="done", devices="exempt"),
        manifest_extra={"quality_scale": "bronze"},
    )

    with pytest.raises(SystemExit) as raised:
        main(["--root", str(root)])

    lines = str(raised.value.code).splitlines()
    assert len(lines) == 3
    assert all(line.startswith("check_quality_scale: ") for line in lines)
