"""What the release gate assumes about the workflows it calls (spec §10.2).

``release.yml`` calls ``test.yml`` and ``validate.yml`` whole. A job that is
``continue-on-error`` in a called workflow fails without failing the caller.
On a tag such a job would let the gate pass over a red row, and §10.2 chose
that both pytest rows block a release.

A called workflow may still carry ``continue-on-error``: §8.7's ``latest`` row
is a signal on pull requests and the monthly cron. But the value must be an
expression that is false on a tag. So the tag guard must be one of the parts
joined by ``&&`` at the top level of the expression. Anything else is
rejected, including a literal and any expression containing ``||``, because
an ``or`` can be true on a tag whatever sits beside it.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CALLED_WORKFLOWS = ("test.yml", "validate.yml")

#: The ``&&`` part that turns a signal into a blocker on a tag. ``github.ref``
#: is the caller's ref inside a reusable workflow, so on a release run it is
#: the pushed tag.
TAG_GUARD = "!startsWith(github.ref, 'refs/tags/')"

CONTINUE_ON_ERROR = re.compile(r"^\s*continue-on-error:\s*(?P<value>.*?)\s*$")
EXPRESSION = re.compile(r"^\$\{\{(?P<body>.*)\}\}$", re.DOTALL)


def _is_guarded(value: str) -> bool:
    """Say whether ``value`` is an expression that a tag ref turns off."""
    expression = EXPRESSION.match(value)
    if expression is None:
        # A literal `true` is on for every ref, and a literal `false` would not
        # be written. Neither is an expression this can reason about.
        return False
    body = expression.group("body")
    if "||" in body:
        return False
    return any(conjunct.strip() == TAG_GUARD for conjunct in body.split("&&"))


def test_called_workflows_never_continue_on_error_on_a_tag() -> None:
    """Every ``continue-on-error`` in a called workflow is guarded, or absent."""
    for name in CALLED_WORKFLOWS:
        text = (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        for line in text.splitlines():
            match = CONTINUE_ON_ERROR.match(line)
            if match is None:
                continue
            assert _is_guarded(match.group("value")), (
                f"{name}: {line.strip()!r} would let release.yml pass over a "
                f"failure. The expression must have `{TAG_GUARD}` as a "
                f"top-level && part"
            )


def test_the_guard_recogniser_is_fail_closed() -> None:
    """The check accepts only expressions that a tag turns off."""
    assert _is_guarded("${{ " + TAG_GUARD + " }}")
    assert _is_guarded("${{ matrix.row == 'latest' && " + TAG_GUARD + " }}")
    assert not _is_guarded("true")
    assert not _is_guarded("${{ matrix.row == 'latest' }}")
    # An `or` can be true on a tag however the guard is written beside it.
    assert not _is_guarded("${{ " + TAG_GUARD + " || matrix.row == 'latest' }}")
    # A negated group is not a top-level part, so it is not accepted.
    assert not _is_guarded("${{ !(" + TAG_GUARD + " && false) }}")
