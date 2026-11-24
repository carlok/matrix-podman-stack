"""One package, one pin: the requirement files installed together must not disagree.

`lint-and-validate` installs requirements-dev.txt, scripts/requirements.txt and
bots/example_bot/requirements.txt in a **single** pip resolution, so a package exact-pinned
in two files only resolves while both numbers happen to match — and nothing made Dependabot
update both. PR #53 broke that way: nats-py was 2.17.0 in the root file and 2.16.0 in the
example bot's, and pip reported ResolutionImpossible instead of anything that pointed at the
duplicate.

The rule these tests enforce: `requirements-dev.txt` owns the exact pins, every other
requirement file declares names or lower bounds, and no package is exact-pinned twice.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIN_SOURCE = "requirements-dev.txt"
OTHER_FILES = ["scripts/requirements.txt", "bots/example_bot/requirements.txt"]
PIN = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*(?P<version>[^\s;#]+)")


def _lines(rel):
    path = ROOT / rel
    if not path.exists():
        return []
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line and not line.startswith(("-r", "-c", "--")):
            out.append(line)
    return out


def _norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def _pins(rel):
    pins = {}
    for line in _lines(rel):
        match = PIN.match(line)
        if match:
            pins[_norm(match.group("name"))] = match.group("version")
    return pins


def test_no_package_is_exact_pinned_in_two_files():
    source = _pins(PIN_SOURCE)
    clashes = {}
    for rel in OTHER_FILES:
        for name, version in _pins(rel).items():
            if name in source:
                clashes.setdefault(name, []).append((rel, version, source[name]))
    assert not clashes, (
        "package exact-pinned both in " + PIN_SOURCE + " and elsewhere, which a single "
        f"pip resolution cannot satisfy once they drift: {clashes}")


def test_other_requirement_files_use_ranges_not_pins():
    offenders = {rel: sorted(_pins(rel)) for rel in OTHER_FILES if _pins(rel)}
    assert not offenders, (
        f"exact pins belong in {PIN_SOURCE} only; these files pin too: {offenders}")


def test_every_bot_requirement_is_covered_by_the_pin_source():
    source = _pins(PIN_SOURCE)
    declared = {_norm(m.group(1)) for rel in OTHER_FILES for m in
                (re.match(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)", line) for line in _lines(rel))
                if m}
    uncovered = sorted(declared - set(source))
    assert not uncovered, (
        f"declared but not version-owned by {PIN_SOURCE}: {uncovered}")
