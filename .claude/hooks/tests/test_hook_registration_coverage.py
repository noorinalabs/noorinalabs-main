#!/usr/bin/env python3
"""Registration-coverage guards for the hook dispatchers — issue #698.

A hook only runs if it is reachable one of exactly two ways:

  * **dispatched** — named in a ``hooks.*`` list in the *resolved* framework
    config, and exposing the dispatcher contract ``check(input_data)``; or
  * **standalone** — registered as its own ``command`` entry in
    ``.claude/settings.json``, invoked as a subprocess (``main()``).

Two silent failure modes live in the gap between those:

  1. A ``check()``-exposing hook reachable *neither* way. Because a supplied
     ``hooks.*`` list REPLACES the default rather than merging (see
     ``_framework_config._deep_merge``), a module dropped from
     ``framework.config.json`` silently stops running even though its ``check()``
     is still on disk.
  2. A module *named* in a ``hooks.*`` list that exposes no ``check()``. The
     dispatchers ``getattr(mod, "check", None)`` and skip on ``None``, so the
     entry reads as enabled and never runs.

Replacement semantics are deliberate — omitting a default is how a repo disables
a hook — so these tests are the safety net that makes an *accidental* omission
loud. Hermetic: modules are parsed with ``ast``, never imported, so no hook side
effect (network, git, ontology I/O) can run here.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[1]
CLAUDE_DIR = HOOKS_DIR.parent
SETTINGS = CLAUDE_DIR / "settings.json"

_CFG_PATH = HOOKS_DIR / "_framework_config.py"
_spec = importlib.util.spec_from_file_location("_framework_config", _CFG_PATH)
assert _spec is not None and _spec.loader is not None
_framework_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_framework_config)

# The dispatchers themselves, plus ``_``-prefixed shared libs, are infrastructure
# rather than hooks: they are never listed in a ``hooks.*`` list.
DISPATCHERS = {"dispatcher", "post_dispatcher"}

# Hooks that intentionally expose ``check()`` while being reachable neither way.
# Empty by design: adding a name here must be a deliberate, reviewed decision
# with a rationale, not the silent default that #698 was.
INTENTIONALLY_UNREGISTERED: set[str] = set()

# Every ``hooks.<event>`` list the dispatchers read. ``dispatcher.py`` reads
# ``pre_bash`` (Bash), ``pre_file`` (Edit/Write) and ``pre_notebook``
# (NotebookEdit, #1114); ``post_dispatcher.py`` reads ``post_bash`` (Bash),
# ``post_file`` (Edit/Write) and ``post_notebook`` (NotebookEdit).
HOOK_LIST_KEYS = ("pre_bash", "pre_file", "pre_notebook", "post_bash", "post_file", "post_notebook")

# A shell tail that swallows a non-zero exit and reports success. Appended to a
# hook ``command`` it converts *"this gate could not run"* (a missing script
# exits 2, which PreToolUse reads as BLOCK) into *"this gate silently allows"* —
# fail-open. Forbidden for IN-TREE registrations; see #828 / #830 / #697 / #698.
#
# The guard flags a ``||``- or ``;``-sequenced tail whose right-hand side is
# anything OTHER than a non-zero ``exit`` — because any such RHS can exit 0 and
# thereby swallow the block. A genuine re-raise (``|| exit 1``, ``; exit 2``) is
# deliberately allowed, as is a bare trailing separator with no RHS.
#   * ``(?:\|\||;)``           — a ``||`` or ``;`` sequencer, then optional space,
#   * ``(?=\S)``               — with a non-empty RHS (skip a bare trailing sep),
#   * ``(?!exit\s+0*[1-9]\d*)`` — that is NOT ``exit <non-zero>``.
_FAIL_OPEN_GUARD = re.compile(r"(?:\|\||;)\s*(?=\S)(?!exit\s+0*[1-9]\d*)")


def _exposes_check(path: Path) -> bool:
    """True if the module defines a top-level ``check`` function. Parse, not import."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "check"
        for node in tree.body
    )


def _hook_modules() -> dict[str, Path]:
    """Every candidate hook module: ``.claude/hooks/*.py`` minus libs + dispatchers."""
    return {
        p.stem: p
        for p in sorted(HOOKS_DIR.glob("*.py"))
        if not p.stem.startswith("_") and p.stem not in DISPATCHERS
    }


def _exposes_main(path: Path) -> bool:
    """True if the module defines a top-level ``main`` function. Parse, not import."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "main"
        for node in tree.body
    )


def _imports_hook_main(path: Path) -> bool:
    """True if the module imports anything from ``_hook_main`` (the main#1121
    consolidated ``run_blocking``/``run_advisory`` entry points)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(
        isinstance(node, ast.ImportFrom) and node.module == "_hook_main" for node in ast.walk(tree)
    )


# Hooks with a top-level ``main()`` deliberately NOT on ``_hook_main``
# (main#1121, epic main#1097). Population = ``_hook_modules()`` filtered to
# those exposing ``main()`` — NOT raw ``_hook_modules()`` membership, because
# ``annunaki_log.py`` is a shared lib living in ``.claude/hooks/`` without an
# underscore prefix: it has no ``main()`` and is not a hook, and gating on raw
# membership would demand a spurious entry for it on day one (#1330 review —
# a gate whose first act is to require a false exclusion teaches its users
# that entries are bureaucratic noise, and every later entry inherits that).
#
# Every entry needs a REASON, not just a name — unlike
# ``INTENTIONALLY_UNREGISTERED`` above (which has stayed a bare ``set()``
# only because it is EMPTY), this mapping ships with entries from day one,
# which is precisely the condition under which a name-only set loses
# provenance. The reasons mirror noorinalabs-main#1329's per-hook rationale —
# keep them in sync; a name added here without updating #1329 (or vice
# versa) is exactly the drift the two are supposed to jointly prevent.
_UNCONVERTED: dict[str, str] = {
    "validate_edit_completion": (
        "check() returns None for any tool_name not in _DISPATCHED_PRE_TOOLS "
        "(= _EDIT_TOOLS | {'Bash'}, L123/L522), and SendMessage is not in it. "
        "main()'s PreToolUse branch calls _pre_tool_use_blocks directly, "
        "bypassing that filter — which is how the SendMessage registration "
        "in settings.json reaches the gate at all. run_blocking(check, ...) "
        "would route SendMessage through the filter and silently return "
        "None, disabling the hook for its only standalone registration."
    ),
    "auto_add_issue_to_board": (
        "standalone main() catches a check() exception and logs it via "
        "log_posttooluse_event, whose 'posttooluse_event' record type is "
        "NOT in annunaki_log.TRACE_RECORD_TYPES — it writes to the COUNTED "
        "errors.jsonl stream, unlike _hook_main's generic swallow "
        "(log_pretooluse_diagnostic -> traces.jsonl, excluded from the "
        "count). Converting would downgrade a deliberately louder existing "
        "signal."
    ),
    "post_label_change_wave_field_sync": (
        "standalone main() catches a check() exception and logs it via "
        "log_posttooluse_event, whose 'posttooluse_event' record type is "
        "NOT in annunaki_log.TRACE_RECORD_TYPES — it writes to the COUNTED "
        "errors.jsonl stream, unlike _hook_main's generic swallow "
        "(log_pretooluse_diagnostic -> traces.jsonl, excluded from the "
        "count). Converting would downgrade a deliberately louder existing "
        "signal."
    ),
    "post_wave_kickoff_comment": (
        "standalone main() catches a check() exception and logs it via "
        "log_posttooluse_event, whose 'posttooluse_event' record type is "
        "NOT in annunaki_log.TRACE_RECORD_TYPES — it writes to the COUNTED "
        "errors.jsonl stream, unlike _hook_main's generic swallow "
        "(log_pretooluse_diagnostic -> traces.jsonl, excluded from the "
        "count). Converting would downgrade a deliberately louder existing "
        "signal."
    ),
    "annunaki_monitor": (
        "standalone main() calls check(input_data) and discards the return "
        "value entirely (side-effect-only; the return value is meaningful "
        "only to the PostToolUse dispatcher's own aggregation). "
        "run_advisory would start printing that return value on standalone "
        "invocation — a stdout-shape change with no compensating benefit."
    ),
    "ontology_tracker": (
        "standalone main() calls check(input_data) and discards the return "
        "value entirely (side-effect-only; the return value is meaningful "
        "only to the PostToolUse dispatcher's own aggregation). "
        "run_advisory would start printing that return value on standalone "
        "invocation — a stdout-shape change with no compensating benefit."
    ),
    "session_start": (
        "SessionStart hook — does not read stdin at all (informational "
        "only); does not fit the check(input_data) -> dict | None contract."
    ),
    "session_handoff": (
        "Stop hook — main() does everything directly (git state, gh calls, "
        "file write); no separate check() function to extract without a "
        "larger refactor."
    ),
}


def test_unconverted_population_matches_hooks_with_main_and_no_hook_main_import() -> None:
    """Every hook module with a top-level ``main()`` must EITHER import
    ``_hook_main`` (the main#1121 consolidated entry points) OR carry a
    reasoned entry in ``_UNCONVERTED``.

    This is the gate that would have caught the straggler a #1330 review
    found by hand: ``block_shutdown_without_retro.py`` had a plain
    boilerplate ``main()`` and was silently absent from BOTH the converted
    set and the documented exclusion list until this test existed.
    """
    modules = _hook_modules()
    population = {name: path for name, path in modules.items() if _exposes_main(path)}

    # Direction 1 — every module with main() that isn't converted must be
    # documented. Catches an ADDITION (a new/edited hook with a boilerplate
    # main() slipping past both the helper and the exclusion list) — the
    # block_shutdown_without_retro.py straggler class a #1330 review found
    # by hand.
    missing = sorted(
        name
        for name, path in population.items()
        if not _imports_hook_main(path) and name not in _UNCONVERTED
    )
    assert not missing, (
        "Hook module(s) have main() but are neither converted to _hook_main "
        "NOR documented in _UNCONVERTED:\n"
        + "".join(
            f"  - {name}.py has no _hook_main import and no _UNCONVERTED entry\n"
            for name in missing
        )
        + "\nEither convert the hook onto _hook_main.run_blocking/run_advisory, "
        "or add a reasoned entry to _UNCONVERTED (and keep "
        "noorinalabs-main#1329 in sync)."
    )

    # Direction 2 — every _UNCONVERTED entry must still apply. Catches a
    # REMOVAL (a module later converted or deleted, whose stale exclusion
    # entry would otherwise sit in the mapping indefinitely, unnoticed) —
    # the self-cleaning half; without it the gate is honest about additions
    # and blind to removals, and the reason strings decay silently.
    stale = sorted(_UNCONVERTED)
    stale_reasons = []
    for name in stale:
        if name not in population:
            stale_reasons.append(f"  - _UNCONVERTED names {name}.py, which no longer exists\n")
        elif _imports_hook_main(population[name]):
            stale_reasons.append(
                f"  - _UNCONVERTED names {name}.py, which now imports _hook_main — "
                "remove the entry\n"
            )
    assert not stale_reasons, (
        "_UNCONVERTED entry(ies) no longer apply — remove them and update "
        "noorinalabs-main#1329:\n" + "".join(stale_reasons)
    )


def test_unconverted_does_not_include_dispatchers() -> None:
    """``dispatcher.py``/``post_dispatcher.py`` are already excluded from the
    population by ``DISPATCHERS``/``_hook_modules()`` — adding them to
    ``_UNCONVERTED`` too would be a duplicate exclusion, exactly the kind of
    drift this gate exists to prevent (#1330 review)."""
    assert not (DISPATCHERS & set(_UNCONVERTED))


def _resolved_config():
    """The live merged config, exactly as a dispatcher resolves it at runtime."""
    _framework_config.clear_cache()
    return _framework_config.config(start_dir=CLAUDE_DIR)


def _dispatched_modules(cfg) -> dict[str, str]:
    """module -> the ``hooks.<event>`` key that dispatches it."""
    out: dict[str, str] = {}
    for key in HOOK_LIST_KEYS:
        for name in cfg.get(f"hooks.{key}", []) or []:
            out.setdefault(name, key)
    return out


def _standalone_modules() -> set[str]:
    """Modules invoked by their own ``command`` entry in settings.json."""
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    found: set[str] = set()
    for matchers in settings.get("hooks", {}).values():
        for matcher in matchers:
            for hook in matcher.get("hooks", []):
                command = hook.get("command", "")
                for stem in _hook_modules():
                    if f"/{stem}.py" in command:
                        found.add(stem)
    return found


def test_every_check_exposing_hook_is_reachable() -> None:
    """A hook implementing ``check()`` must be dispatched or standalone-registered.

    This is the guard that would have caught a hook silently dropped from the
    ``hooks.*`` lists (#698).
    """
    cfg = _resolved_config()
    dispatched = set(_dispatched_modules(cfg))
    standalone = _standalone_modules()

    orphans = sorted(
        name
        for name, path in _hook_modules().items()
        if _exposes_check(path)
        and name not in dispatched
        and name not in standalone
        and name not in INTENTIONALLY_UNREGISTERED
    )

    assert not orphans, (
        "Hook module(s) expose check() but are never executed — dead code:\n"
        + "".join(f"  - {name}\n" for name in orphans)
        + f"\nA supplied hooks.* list in {SETTINGS.parent.name}/framework.config.json "
        "REPLACES the default list in _framework_config._DEFAULTS, so a module "
        "omitted there is silently dropped.\n"
        "Remedy — pick one:\n"
        "  (a) dispatch it: add the module to the appropriate hooks.<event> list "
        "in .claude/framework.config.json (and keep _DEFAULTS in sync); or\n"
        "  (b) register it standalone: add a command entry running "
        "<module>.py to .claude/settings.json.\n"
        "If it is genuinely meant to run nowhere, delete it — or add it to "
        "INTENTIONALLY_UNREGISTERED in this file with a written rationale."
    )


def test_every_dispatched_module_exposes_check() -> None:
    """A module named in a resolved ``hooks.*`` list must implement ``check()``.

    The dispatchers skip a module without one, so the entry reads as enabled and
    never runs — the inverse of the orphan above (#698).
    """
    cfg = _resolved_config()
    modules = _hook_modules()
    inert: list[str] = []

    for name, key in _dispatched_modules(cfg).items():
        path = modules.get(name)
        if path is None or not _exposes_check(path):
            missing = "no such module" if path is None else "no check()"
            inert.append(f"  - {name} (hooks.{key}: {missing})\n")

    assert not inert, (
        "Config lists module(s) the dispatcher cannot run — inert entries:\n"
        + "".join(inert)
        + "\nEvery dispatched module must define a top-level "
        "check(input_data) -> dict | None.\n"
        "Remedy — pick one:\n"
        "  (a) give the module a check() so the dispatcher runs it; or\n"
        "  (b) drop it from the hooks.<event> list — if it is standalone-registered "
        "in .claude/settings.json it already runs, and the list entry is a lie."
    )


def test_defaults_hook_lists_expose_check() -> None:
    """``_DEFAULTS`` is the template a config-less repo runs on — hold it to the
    same contract, so a fresh checkout does not inherit inert entries."""
    modules = _hook_modules()
    defaults = _framework_config._DEFAULTS["hooks"]
    inert = sorted(
        f"{key}:{name}"
        for key, names in defaults.items()
        for name in names
        if name not in modules or not _exposes_check(modules[name])
    )
    assert not inert, (
        "_framework_config._DEFAULTS names module(s) without a check() — they "
        f"would never run in a repo with no framework.config.json: {inert}"
    )


def test_config_file_matches_defaults() -> None:
    """The committed ``framework.config.json`` hooks and ``_DEFAULTS['hooks']``
    must agree.

    The two are meant to be a mirror (the JSON is the live source of truth; the
    Python defaults are its config-less shadow). A drift between them means a
    fresh checkout runs a different gate set than a configured one — exactly the
    silent divergence this suite exists to forbid.
    """
    cfg_file = json.loads((CLAUDE_DIR / "framework.config.json").read_text(encoding="utf-8"))
    assert cfg_file.get("hooks") == _framework_config._DEFAULTS["hooks"], (
        "framework.config.json 'hooks' and _framework_config._DEFAULTS['hooks'] "
        "have drifted. Keep them in sync — the JSON is the source of truth; "
        "_DEFAULTS is the fallback a config-less checkout runs on."
    )


def test_block_squash_wave_merge_is_dispatched_last() -> None:
    """The squash guard is wired, and ordered after the local-only checks.

    It resolves a PR base via ``gh pr view``, so it must not gate cheap checks
    behind a network call. Pinning the position keeps the dispatcher's documented
    "cheap/local first, network-calling last" ordering honest.
    """
    pre_bash = _resolved_config().get("hooks.pre_bash", [])
    assert "block_squash_wave_merge" in pre_bash, (
        "block_squash_wave_merge must be dispatched — it is the only enforcement "
        "of --merge over --squash for integration-branch merges (#698)."
    )
    assert pre_bash[-1] == "block_squash_wave_merge", (
        "block_squash_wave_merge issues a `gh pr view` call and must run last in "
        f"hooks.pre_bash; found order: {pre_bash}"
    )


def test_smart_grep_ontology_precedes_block_bare_grep() -> None:
    """smart_grep_ontology must run before the block_bare_grep backstop (#1017).

    A symbol-shaped rg/grep is answered inline by the ontology router; if the
    bare-grep block ran first it would reject the command before the router got
    a chance, defeating the point.
    """
    pre_bash = _resolved_config().get("hooks.pre_bash", [])
    assert "smart_grep_ontology" in pre_bash and "block_bare_grep" in pre_bash
    assert pre_bash.index("smart_grep_ontology") < pre_bash.index("block_bare_grep"), (
        "smart_grep_ontology must precede block_bare_grep in hooks.pre_bash; "
        f"found order: {pre_bash}"
    )


def _settings_commands() -> list[tuple[str, str]]:
    """(event, command) for every hook command registered in settings.json."""
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    out: list[tuple[str, str]] = []
    for event, matchers in settings.get("hooks", {}).items():
        for matcher in matchers:
            for hook in matcher.get("hooks", []):
                out.append((event, hook.get("command", "")))
    return out


def test_no_intree_registration_fails_open() -> None:
    """No `.claude/settings.json` hook command may swallow a run failure.

    Every command in the *tracked* ``settings.json`` is an **in-tree**
    registration — it invokes ``$CLAUDE_PROJECT_DIR/.claude/hooks/<script>.py``,
    which lives in the same commit as this entry and cannot decouple from it.
    Any ``||``- or ``;``-sequenced tail whose RHS is not a non-zero ``exit``
    would convert a hand-deleted script's loud BLOCK (exit 2) into a silent
    ALLOW — the fail-open footgun #828 was filed to forbid, #830 to document,
    and #851 to broaden this guard against.
    """
    offenders = [
        f"  - {event}: {command}\n"
        for event, command in _settings_commands()
        if _FAIL_OPEN_GUARD.search(command)
    ]

    assert not offenders, (
        "In-tree hook registration(s) in .claude/settings.json fail OPEN:\n"
        + "".join(offenders)
        + "\nAn in-tree hook and its settings.json registration are tracked in "
        "the same commit and cannot decouple, so a `||`/`;`-sequenced tail whose "
        "RHS is not a non-zero `exit` (e.g. `|| exit 0`, `|| true`, `; exit 0`, "
        "`|| echo x`) only turns a hand-deleted script's loud BLOCK into a silent "
        "ALLOW (fail-open — #697/#698). Drop the guard: a security gate that "
        "cannot run must fail closed."
    )


# --- Direct bite-tests on _FAIL_OPEN_GUARD (#851) ------------------------------
# The consumer test above exercises the guard only through the live settings.json,
# which today has zero offenders — so it stays green no matter how broad OR narrow
# the regex is. These pin the guard's BOUND directly.

# The in-tree registration form every tracked settings.json command takes.
_REGISTRATION = 'python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/some_gate.py'

# Tails that convert a missing-script BLOCK (exit 2) into a silent ALLOW — the
# guard MUST flag each.
_SWALLOW_TAILS = [
    "|| exit 0",
    "|| true",
    "|| :",
    "; exit 0",
    "|| echo skip",
    "|| printf skip",
    "|| cat",
    "|| exit 000",
    "|| exit 00",
]

# Tails (or their absence) that CANNOT swallow a block: a genuine fail-CLOSED
# re-raise (non-zero ``exit``), a bare command, or a bare trailing separator.
_SAFE_TAILS = [
    "",  # the bare registration, no tail
    "|| exit 1",
    "; exit 2",
    "|| exit 010",
    "|| exit 42",
    ";",  # bare trailing separator
]


@pytest.mark.parametrize("tail", _SWALLOW_TAILS)
def test_fail_open_guard_flags_swallow_tails(tail: str) -> None:
    """Every block-swallowing tail must be caught by ``_FAIL_OPEN_GUARD``."""
    command = f"{_REGISTRATION} {tail}"
    assert _FAIL_OPEN_GUARD.search(command), (
        f"_FAIL_OPEN_GUARD failed to flag a fail-open tail: {tail!r} — its RHS can "
        "exit 0 and swallow the missing-script BLOCK. A narrowing re-opens #851."
    )


@pytest.mark.parametrize("tail", _SAFE_TAILS)
def test_fail_open_guard_allows_safe_tails(tail: str) -> None:
    """A fail-CLOSED re-raise, a bare command, or a bare separator must NOT flag."""
    command = f"{_REGISTRATION} {tail}".rstrip()
    assert not _FAIL_OPEN_GUARD.search(command), (
        f"_FAIL_OPEN_GUARD false-flagged a legitimate registration tail: {tail!r}. "
        "A non-zero `exit` fails CLOSED and a bare separator exits with the LHS "
        "status — neither swallows a block."
    )
