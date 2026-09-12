"""Assert the conformance register and the probe that verifies it agree.

``docs/conformance/checklist.md`` is a living register with seven columns and a
fixed vocabulary, and ``scripts/probe.py`` runs its automated rows. Nothing
upstream reads either, so the ways they can drift are checked here or nowhere:
a duplicated or malformed id, a word outside the vocabulary, a firmware nobody
has captured, evidence that does not resolve, a dependents cell with no
resolvable reference, a manual row without its procedure, a summary line whose
figures no longer match the table, and — the one place the two files can
silently diverge — a set of automated ids the probe does not register exactly.

The summary line under the table is hand-written prose, but its figures are
the check's contract. It must be one bold sentence of exactly this shape, on
its own line::

    **48 verified at firmware 1.21, 10 open, 12 `disagrees`.**

followed by whatever prose the register wants. The three counts are held to
the table: rows whose status is ``verified fw <that firmware>``, rows whose
status is ``open``, and rows whose ``vs spec`` is ``disagrees``.

Run from ``scripts/check.sh``. Silent when the register is clean; otherwise
prints one line per problem and exits non-zero. The escape hatch is the
vocabulary itself: ``manual`` tier and ``open`` status ask for nothing.
"""

import importlib.util
import re
import sys
from pathlib import Path

import probe

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTER_PATH = REPO_ROOT / "docs" / "conformance" / "checklist.md"
CONST_PATH = REPO_ROOT / "custom_components" / "heatit_wifi_panel" / "const.py"

VS_SPEC = frozenset({"agrees", "disagrees", "silent"})
TIERS = frozenset({*probe.TIERS, probe.MANUAL})
STATUS = re.compile(r"^(?:open|(?P<kind>verified|contradicted) fw (?P<firmware>\S+))$")

#: An evidence or dependents entry resolves as one of these three kinds.
ISSUE_LINK = re.compile(
    r"\[#\d+\]\(https://github\.com/[\w.-]+/[\w.-]+/(?:issues|pull)/\d+\)"
)
PROCEDURE_LINK = re.compile(r"\[(?P<name>P-\d+)\]\(#(?P<anchor>p-\d+)\)")
BACKTICKED = re.compile(r"`([^`]+)`")
PROCEDURE_HEADING = re.compile(r"^### (P-\d+)\b", re.MULTILINE)
PROCEDURE_ANCHOR = re.compile(r'<a id="(p-\d+)"></a>')
SUMMARY_LINE = re.compile(
    r"^\*\*(?P<verified>\d+) verified at firmware (?P<firmware>\S+), "
    r"(?P<open>\d+) open, (?P<disagrees>\d+) `disagrees`\.\*\*",
    re.MULTILINE,
)
NO_EVIDENCE = "—"


def procedures_defined(text: str) -> frozenset[str]:
    """Return the ``P-n`` ids the appendix defines, by heading and by anchor."""
    headings = set(PROCEDURE_HEADING.findall(text))
    anchors = {anchor.upper() for anchor in PROCEDURE_ANCHOR.findall(text)}
    return frozenset(headings & anchors)


def procedures_cited(cell: str) -> list[str]:
    """Return the ``P-n`` ids a cell cites."""
    return [match.group("name") for match in PROCEDURE_LINK.finditer(cell)]


def entry_resolves(entry: str, *, repo_root: Path, procedures: frozenset[str]) -> bool:
    """Whether an entry is an issue link, a defined procedure, or an existing path."""
    if ISSUE_LINK.fullmatch(entry):
        return True
    procedure = PROCEDURE_LINK.fullmatch(entry)
    if procedure:
        return procedure.group("name") in procedures
    backticked = BACKTICKED.fullmatch(entry)
    if backticked:
        return (repo_root / backticked.group(1)).exists()
    return False


def cell_references(cell: str) -> list[str]:
    """Return every reference-shaped token in a cell, prose left behind."""
    tokens = [match.group(0) for match in ISSUE_LINK.finditer(cell)]
    tokens += [match.group(0) for match in PROCEDURE_LINK.finditer(cell)]
    tokens += [
        match.group(0)
        for match in BACKTICKED.finditer(cell)
        if "/" in match.group(1) or "." in match.group(1)
    ]
    return tokens


def check_shape(
    cells: tuple[str, ...], seen: set[str]
) -> tuple[list[str], probe.Row | None]:
    """Condition 1: id well-formed and unique, seven columns, vocabulary held.

    Returns the problems and the row, or ``None`` when the column count is
    wrong and no row can be built from the cells.
    """
    row_id = cells[0] if cells else "?"
    problems: list[str] = []
    if not probe.ROW_ID.fullmatch(row_id):
        problems.append(f"{row_id}: malformed id")
    if row_id in seen:
        problems.append(f"{row_id}: duplicate id")
    seen.add(row_id)
    if len(cells) != len(probe.REGISTER_COLUMNS):
        problems.append(f"{row_id}: {len(cells)} cells, must be 7 columns")
        return problems, None
    row = probe.row_from_cells(cells)
    if row.vs_spec not in VS_SPEC:
        problems.append(
            f"{row_id}: vs spec {row.vs_spec!r} is not in {sorted(VS_SPEC)}"
        )
    if row.tier not in TIERS:
        problems.append(f"{row_id}: tier {row.tier!r} is not in {sorted(TIERS)}")
    if not STATUS.fullmatch(row.status):
        problems.append(
            f"{row_id}: status {row.status!r} is not open, verified fw <v> "
            f"or contradicted fw <v>"
        )
    return problems, row


def check_firmware(row: probe.Row, verified_firmwares: frozenset[str]) -> list[str]:
    """Condition 2: a verified or contradicted row names a captured firmware."""
    match = STATUS.fullmatch(row.status)
    if match is None or match.group("firmware") is None:
        return []
    firmware = match.group("firmware")
    if firmware in verified_firmwares:
        return []
    message = (
        f"{row.row_id}: {row.status!r} names firmware {firmware!r}, not in "
        f"VERIFIED_FIRMWARES {sorted(verified_firmwares)}"
    )
    return [message]


def check_evidence(
    row: probe.Row, *, repo_root: Path, procedures: frozenset[str]
) -> list[str]:
    """Condition 3: a non-open row has evidence, and every entry resolves."""
    entries = [entry.strip() for entry in row.evidence.split(",") if entry.strip()]
    if entries == [NO_EVIDENCE] or not entries:
        if row.status == "open":
            return []
        return [f"{row.row_id}: {row.status!r} with no evidence"]
    return [
        f"{row.row_id}: evidence entry {entry!r} does not resolve"
        for entry in entries
        if not entry_resolves(entry, repo_root=repo_root, procedures=procedures)
    ]


def check_dependents(
    row: probe.Row, *, repo_root: Path, procedures: frozenset[str]
) -> list[str]:
    """Condition 4: a dependents cell carries at least one resolvable reference."""
    references = cell_references(row.dependents)
    if any(
        entry_resolves(reference, repo_root=repo_root, procedures=procedures)
        for reference in references
    ):
        return []
    return [f"{row.row_id}: dependents cell carries no resolvable reference"]


def check_procedures(rows: list[probe.Row], procedures: frozenset[str]) -> list[str]:
    """Condition 5: open manual rows cite a procedure; every procedure is cited."""
    problems = [
        f"{row.row_id}: open manual row cites no procedure"
        for row in rows
        if row.tier == probe.MANUAL
        and row.status == "open"
        and not procedures_cited(row.evidence)
    ]
    cited = {name for row in rows for name in procedures_cited(row.evidence)}
    problems += [
        f"{name}: appendix procedure cited by no row"
        for name in sorted(procedures - cited)
    ]
    return problems


def check_probe_ids(rows: list[probe.Row], probe_ids: frozenset[str]) -> list[str]:
    """Condition 6: the non-manual ids are exactly the ids probe.py registers."""
    automated = {row.row_id for row in rows if row.tier != probe.MANUAL}
    problems = [
        f"{row_id}: automated in the register but not registered in probe.py"
        for row_id in sorted(automated - probe_ids)
    ]
    problems += [
        f"{row_id}: registered in probe.py but not an automated row in the register"
        for row_id in sorted(probe_ids - automated)
    ]
    return problems


def check_summary(text: str, rows: list[probe.Row]) -> list[str]:
    """Condition 7: the summary line's three figures match the table."""
    match = SUMMARY_LINE.search(text)
    if match is None:
        return [
            (
                "summary line: none found in the form "
                "**<n> verified at firmware <v>, <n> open, <n> `disagrees`.**"
            )
        ]
    firmware = match.group("firmware")
    counted = {
        "verified": sum(row.status == f"verified fw {firmware}" for row in rows),
        "open": sum(row.status == "open" for row in rows),
        "disagrees": sum(row.vs_spec == "disagrees" for row in rows),
    }
    return [
        f"summary line: says {match.group(figure)} {figure}, "
        f"the table has {counted[figure]}"
        for figure in ("verified", "open", "disagrees")
        if int(match.group(figure)) != counted[figure]
    ]


def problems(
    text: str,
    *,
    repo_root: Path,
    verified_firmwares: frozenset[str],
    probe_ids: frozenset[str],
) -> list[str]:
    """Return every problem with a register text; empty when it is clean."""
    all_cells = probe.parse_register_cells(text)
    if not all_cells:
        return ["no register table found"]
    procedures = procedures_defined(text)
    seen: set[str] = set()
    found: list[str] = []
    rows: list[probe.Row] = []
    for cells in all_cells:
        shape, row = check_shape(cells, seen)
        found += shape
        if row is not None:
            rows.append(row)
    for row in rows:
        found += check_firmware(row, verified_firmwares)
        found += check_evidence(row, repo_root=repo_root, procedures=procedures)
        found += check_dependents(row, repo_root=repo_root, procedures=procedures)
    found += check_procedures(rows, procedures)
    found += check_probe_ids(rows, probe_ids)
    found += check_summary(text, rows)
    return found


def verified_firmwares(path: Path = CONST_PATH) -> frozenset[str]:
    """Read ``VERIFIED_FIRMWARES`` from ``const.py`` by path, without the package.

    Loading the file directly keeps the integration's own imports — Home
    Assistant, once the package grows — out of a check that needs one constant.
    """
    spec = importlib.util.spec_from_file_location("heatit_const", path)
    if spec is None or spec.loader is None:
        msg = f"cannot load {path}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    firmwares = module.VERIFIED_FIRMWARES
    if not isinstance(firmwares, frozenset) or not all(
        isinstance(item, str) for item in firmwares
    ):
        msg = f"{path}: VERIFIED_FIRMWARES must be a frozenset of str"
        raise TypeError(msg)
    return firmwares


def main() -> None:
    """Run every condition over the committed register; exit non-zero if any speaks."""
    found = problems(
        REGISTER_PATH.read_text(encoding="utf-8"),
        repo_root=REPO_ROOT,
        verified_firmwares=verified_firmwares(),
        probe_ids=probe.registered_ids(),
    )
    if found:
        sys.exit("\n".join(f"check_conformance: {problem}" for problem in found))


if __name__ == "__main__":
    main()
