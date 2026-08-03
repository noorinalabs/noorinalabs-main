#!/usr/bin/env python3
"""Tests for validate_vps_host.py — BUG-09 lazy-load fix + main() consolidation
(main#1121).

BUG-09: `CLOUDFLARE_RANGES` used to be populated by a MODULE-IMPORT-TIME call
to `_load_cloudflare_ranges()` — every import of this module (every dispatch,
even for a Bash command with nothing to do with VPS_HOST) paid a cache read,
or up to two 3-second network fetches on a cold cache. This suite proves the
lazy replacement only loads on first actual use.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_vps_host as vvh  # noqa: E402


class LazyLoadTests(unittest.TestCase):
    def setUp(self) -> None:
        # Reset the module-level memo between tests — it's a process-lifetime
        # cache by design (BUG-09 fix), so tests must not leak state.
        vvh._cloudflare_ranges_cache = None

    def tearDown(self) -> None:
        vvh._cloudflare_ranges_cache = None

    def test_no_module_level_eager_attribute(self) -> None:
        """The pre-fix `CLOUDFLARE_RANGES` name must be gone — its mere
        existence as a module attribute would mean it was set at import
        time, reintroducing BUG-09."""
        self.assertFalse(hasattr(vvh, "CLOUDFLARE_RANGES"))

    def test_loader_not_called_until_first_real_use(self) -> None:
        with mock.patch.object(vvh, "_load_cloudflare_ranges", return_value=[]) as mock_load:
            mock_load.assert_not_called()  # importing the module alone must not call it
            vvh.is_cloudflare_ip("1.2.3.4")
            mock_load.assert_called_once()

    def test_loader_called_at_most_once_across_multiple_checks(self) -> None:
        """Memoized — repeated Bash commands within one process (the
        dispatcher's in-process loop) must not re-fetch/re-read the cache
        file per call."""
        with mock.patch.object(vvh, "_load_cloudflare_ranges", return_value=[]) as mock_load:
            vvh.is_cloudflare_ip("1.2.3.4")
            vvh.is_cloudflare_ip("5.6.7.8")
            vvh.is_cloudflare_ip("9.9.9.9")
        mock_load.assert_called_once()

    def test_unrelated_command_never_triggers_the_loader(self) -> None:
        """The actual bug: a totally unrelated Bash command (e.g. `ls`)
        dispatched through this module must never reach the loader at all —
        check() short-circuits on the regex match, and now that this is lazy
        the loader is never called in this path."""
        with mock.patch.object(vvh, "_load_cloudflare_ranges", return_value=[]) as mock_load:
            result = vvh.check({"tool_name": "Bash", "tool_input": {"command": "ls -la"}})
        self.assertIsNone(result)
        mock_load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
