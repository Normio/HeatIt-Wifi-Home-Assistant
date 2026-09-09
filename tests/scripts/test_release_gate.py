"""What the release gate assumes about the workflows it calls (spec §10.2).

``release.yml`` calls ``test.yml`` and ``validate.yml`` whole. A job that is
``continue-on-error`` in a called workflow fails without failing the caller,
so such a job on a tag would let the gate pass over a red row — and §10.2
chose, deliberately, that both pytest rows block a release. The only
``continue-on-error`` the called workflows may carry is one that is off on a
tag.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CALLED_WORKFLOWS = ("test.yml", "validate.yml")

#: The one accepted value: a signal on pull requests, a blocker on a tag.
#: ``github.ref`` is the caller's ref inside a reusable workflow.
TAG_GUARD = "${{ !startsWith(github.ref, 'refs/tags/') }}"

CONTINUE_ON_ERROR = re.compile(r"^\s*continue-on-error:\s*(?P<value>.*?)\s*$")


def test_called_workflows_never_continue_on_error_on_a_tag() -> None:
    """Every ``continue-on-error`` in a called workflow is guarded, or absent."""
    for name in CALLED_WORKFLOWS:
        text = (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        for line in text.splitlines():
            match = CONTINUE_ON_ERROR.match(line)
            if match is None:
                continue
            assert match.group("value") == TAG_GUARD, (
                f"{name}: {line.strip()!r} would let release.yml pass over a "
                f"failure; use continue-on-error: {TAG_GUARD}"
            )
