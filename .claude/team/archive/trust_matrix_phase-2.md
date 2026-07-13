# Trust Identity Matrix — Phase 2 archive

> Archived byte-for-byte from `.claude/team/trust_matrix.md`
> at phase close (#964, meta #960), preserving original file order. Do not edit —
> append-only history; new entries go to the live file for the current phase.

---

## Session 7 Trust Updates (2026-04-10) — Phase 2 Wave 1 (Post-Extraction Stabilization)

### Orchestrator → Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Wanjiku Mwangi (TPM) | 3 | **4** ↑ | 3 PRs (2 bug fixes + dispatcher consolidation), zero must-fix items, all reviews approved on first pass. Dispatcher reduced 12 process spawns to 1. Strongest contributor this wave. |
| Santiago Ferreira (RC) | 5 | 5 | 2 clean PRs (CI workflow + release tagging). CI had pre-existing lint failure (not introduced by his code). Already at max. |
| Aino Virtanen (SQL) | 5 | 5 | 1 PR (label naming hook), reviewed all 7 PRs as second reviewer, all approved. Already at max. |
| Nadia Khoury (PD) | 4 | 4 | 1 PR (Redis health check security fix in deploy), clean delivery. Coordination role adequate. No change. |

### Done Well / Needs Improvement (Phase 2 Wave 1)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Wanjiku Mwangi** | 3 PRs covering critical bug fixes and major tech-debt (dispatcher). All clean, zero must-fix. | None this wave |
| **Santiago Ferreira** | CI workflow for hooks (new infrastructure), release tagging cadence (process formalization). Both well-documented. | Pre-existing lint issues not caught before merge — CI introduced by his PR fails on his own branch |
| **Aino Virtanen** | Label naming convention hook, 7 reviews as second reviewer. Consistent quality gate. | None this wave |
| **Nadia Khoury** | Redis health check fix (security), coordination of wave execution | None this wave |

---

## Phase 2 Wave 8 Trust Updates (2026-04-17) — CI Hygiene

### Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Wanjiku Mwangi (TPM) | 4 | 4 | 4 PRs across 4 repos for #111 (main #115, isnad-graph #811, user-service #60, design-system #56), all merged clean. Filed high-quality tech-debt issues with forensic detail (#810, #812, #54, etc.). Handled load-bearing breadcrumb retrofit cleanly across session boundary. No negatives. |
| Santiago Ferreira (RC) | 5 | 5 | 3 PRs for #110 (ruff autoformat in pre-commit): isnad-graph #808, user-service #58, data-acquisition #27. Clean delivery after commit-identity roster-blocker unblocked by Steven. Already at max. |
| Aino Virtanen (SQL) | 5 | 5 | Implemented #109 CI gate hook solo (PR #122), caught spec substitution proactively (`gh pr checks --json` → `statusCheckRollup`), reviewed 7 W8 PRs as charter enforcer, zero must-fix items received. Already at max. |
| Nadia Khoury (PD) | 5 | 5 | Light involvement — reviewed PR #122 with thorough spec-fidelity audit. Already at max, no change. |

### Done Well / Needs Improvement (Phase 2 Wave 8)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Wanjiku Mwangi** (TPM) | Forensic tech-debt filing during #111 sweep (caught hook bugs #113, #118, plus classic-Projects deprecation workaround via REST PATCH). Clean multi-repo delivery. | Had to rework PR bodies post-review when disable-with-followup rule was ratified mid-wave — workflow, not her fault |
| **Santiago Ferreira** (RC) | Batched ruff-format across 3 Python repos efficiently. Review quality matched charter format on all #110 PRs. | Hit commit-identity roster-blocker on 3 of 4 child repos — unblocked by Steven authorizing cross-repo roster merge (long-term fix: #112) |
| **Aino Virtanen** (SQL) | #109 implementation matched existing hook patterns exactly. Handled spec-discrepancy (nonexistent `gh pr checks --json bucket,name,state` flag combo) transparently in PR body. Thorough reviewer across the wave. | None this wave |
| **Nadia Khoury** (PD) | Spec-fidelity review of #122 was executive-quality — validated substitution, checked dispatcher position, flagged program-level concerns (Hook 7 stacking) | Limited involvement — other members carried the wave; appropriate for a wave with tight scope |



---

## Phase 2 Wave 9 Trust Updates (2026-04-22) — Data Pipeline + Hook-Architecture Mini-Sprint

### Org-Level Team (noorinalabs-main)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Wanjiku Mwangi (TPM) | 4 | **5** ↑ | Dual-role wave: implementer on ip#21 (normalize D-ii rewire + topics.py) AND reviewer on main#180, #178, #183, ip#21. Caught main#183 session-start path regression filed as #184. Sustained high output at quality bar for 5 days. Max trust. |
| Santiago Ferreira (RC) | 5 | 5 | Consistent release-coordinator signal: reviewed #180 with branch-enumeration walk-through, approved #187 with dispatcher-position + fail-open analysis. Already at max. |
| Aino Virtanen (SQL) | 5 | 5 | Heavyweight hook-author for the wave: main#174 sentinel, #180 regex unblocker, #183 skill cwd, 6 child-repo #112-b syncs, plus ontology cleanup. Already at max; no ceiling. |
| Nadia Khoury (PD) | 4 | 4 | Strategic review on #174 (sentinel fallback pattern), filed #176 + #177 as followups. Appropriate coordination scope. No change. |
| Weronika Zielinska (PA) | 3 | **4** ↑ | Material architectural contribution: `coalesce(row.props.<f>, n.<f>)` per-field Phase-4 safety is a genuine improvement over the spec I sketched. Caught cross-PR shape mismatch during her own implementation (filed isnad-graph#842 for GRADED_BY gap). #18 D-ii rewire shipped clean on first re-review. |

### Child-Repo Teams — New Entries / Updates

#### noorinalabs-user-service team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Mateo Salazar (Eng) | — | **4** (new) | user-service#77 OAuth override + security-fixup cycle. Apple `aud`/`issuer` exemption call + scope-disciplined #76 tech-debt filing. Changes-Requested → clean-fixup → merge in one pass. |
| Idris Yusuf (Sec Eng) | — | **4** (new) | Single-review prevention of production credential-exfil vector (no env-guard on OAuth override). Filed user-service#78 as hard blocker before approving — exactly the right pattern. |
| Anya Kowalczyk (TL) | — | **3** (new) | Tech-lead review of user-service#77 with architectural fit analysis (override scheme+netloc abstraction, 13-call-site coverage audit). Path-in-override nit still open as minor followup. |

#### noorinalabs-data-acquisition team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Kwesi Boateng (Integration Eng) | — | **4** (new) | data-acquisition#30 Kafka emit + fixup after 4-blocker Changes-Requested. Scope discipline on kafka-python decision + future-compat b2_key construction + topic-name mismatch flagging. Also shipped #31 (.new → .landed rename) cleanly. |
| Dilara Erdogan (Pipeline Mgr) | — | **4** (new) | Manager review on #30 — filed noorinalabs-main#190 as cross-repo tracking issue during review. That filing became central to the #192 design call. |
| Alejandra Reyes-Fuentes (Staff Data Eng) | — | **4** (new) | Code-level review on #30 with 4 substantive technical findings (future.get defeating batching, no jitter on retry, validator gaps, ISO date slice). Every finding was a real bug. |

#### noorinalabs-isnad-graph team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Farhan Malik (Data Eng Lead) | — | **4** (new) | Reviewer on ip#18 — caught Phase-4 safety violation (`SET n += row.props`) that materially reshaped the final ingest design. Re-reviewed post-rewire and filed isnad-graph#843 as parallel followup to his own earlier-filed #842. |
| Arjun Raghavan (System Architect) | — | **4** (new) | Reviewer on ip#18 pre + post-rewire. Filed ip#19, #20, #23, #24 — four legitimate tech-debt followups at appropriate severity levels. |

#### noorinalabs-deploy team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Lucas Ferreira (SRE) | 3 | 3 | deploy#146 shipped with red CI (GET vs POST callback shape mismatch) — recovery via fixup #149 was clean and surfaced user-service#79 + deploy#148 process gaps. Minor ding offset by recovery discipline. Holding at 3. |
| Aisha Idrissi (SRE) | — | **4** (new) | Multi-role wave: implemented main#114 (auto_set_env_test fix) + reviewed deploy#146/#149 with network-topology and healthcheck analysis. Filed deploy#147 image-size reconciliation. |
| Nino Kavtaradze (Sec Eng) | — | **4** (new) | Security review on deploy#146 with comprehensive enumeration (prod compose untouched, no id_token signing surface, no host port leakage, fake creds grep-checked). |
| Bereket Tadesse (Infra Mgr) | — | **3** (new) | Appeared as review routing target (wasn't actually spawned this wave) + #177 post-merge verification executed cleanly by the fresh-spawn identity. |

### Done Well / Needs Improvement (Phase 2 Wave 9)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Wanjiku Mwangi** (TPM) | 5-day sustained delivery: #180 branch-regex, #21 D-ii rewire + topics.py, multiple clean reviews. Caught main#183 session-start regression + filed #184. | None this wave. |
| **Aino Virtanen** (SQL) | Heavy hook-author output: #174, #180, #183, #112-b × 6 child repos + ontology cleanup. Divergent-hook transparency pattern on #112-b was exactly right. | Initial session-start path regression on #183 (recovered in fixup same session). |
| **Weronika Zielinska** (PA) | `coalesce` Phase-4 approach was a material improvement over spec. Cross-PR shape-mismatch detection during own implementation. | None this wave. |
| **Mateo Salazar** (user-service Eng) | Security-fixup-inline over defer-to-followup (user-service#78 closed at merge, not left to tech-debt). | None this wave. |
| **Idris Yusuf** (user-service Sec) | Prevention-of-production-vulnerability review. Textbook security signal. | None this wave. |
| **Kwesi Boateng** (data-acquisition Int) | Changes-Requested → clean-fixup cycle worked exactly as designed. Topic-name reconciliation flagging in PR body led to right tracking. | None this wave. |
| **Alejandra Reyes-Fuentes** (data-acquisition Staff DE) | Four real technical findings on #30 — no false positives, all addressed in fixup. | None this wave. |
| **Farhan Malik** (isnad-graph DE Lead) | Phase-4 safety catch was the pivot point of the ip#18 rewire. Co-filed #842/#843 edge-model gaps. | None this wave. |
| **Arjun Raghavan** (isnad-graph Arch) | Four legitimate tech-debt followups at appropriate severity (coalesce null-asymmetry, property-map drift, retry compounding, schema source-of-truth). | None this wave. |
| **Lucas Ferreira** (deploy SRE) | Deploy#146 fixup recovery within 30 min; surfacing #79 + #148. | Merged deploy#146 with red CI — cross-verification against `gh pr checks` before `gh pr merge` would have prevented. |
| **Aisha Idrissi** (deploy SRE) | Auto_set_env fix shipped clean; review on deploy#146 network-topology was right-depth. | None this wave. |
| **Nino Kavtaradze** (deploy Sec) | Comprehensive deploy#146 security enumeration with grep-verified fake-creds non-leakage. | None this wave. |
| **Santiago Ferreira** (RC) | Consistent release-coordinator analysis on #180 and #187. | None this wave. |
| **Nadia Khoury** (PD) | Strategic sentinel-pattern review on #174 with followup filing discipline. | None this wave. |
| **Bereket Tadesse** (Infra Mgr) | Clean #177 verification with honest intermittency caveat. | None this wave. |
| **Orchestrator** | Volume execution across 4 repos; team-simulation scaled cleanly. | 2 red-CI merges (main#178, deploy#146); late design call for ip#18/#21 mismatch; premature "wave-9 concluded" handoff claim requiring user correction. |


---

## Phase 2 Wave 10 Trust Updates (2026-04-30) — Stg/Prod Environment Split + Promotion Pathway

### Org-Level Team (noorinalabs-main)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aino Virtanen (SQL) | 5 | 5 | Hook 17 `validate_wave_audit` shipped in `main#218` — load-bearing wave-conclusion gate. Charter updates (agents.md single-session-team delegation, hooks.md, issues.md) plus continued ontology hygiene. Already at max. |
| Nadia Khoury (PD) | 4 | 4 | Drove 5-repo wave-merge ceremony, resolved `user-service#89` ghcr-publish.yml union conflict, filed `main#222` branch-protection remediation tracker. Coordination-class output. No change. |
| Wanjiku Mwangi (TPM) | 5 | 5 | Cross-repo wave-coordination + project-board hygiene. Already at max. |
| Santiago Ferreira (RC) | 5 | 5 | §3.0.a TODO marker resolution closing `main#211`; secrets-audit migration runbook contributions. Already at max. |
| Bereket Tadesse (Infra Mgr) | 3 | **4** ↑ | Drafted comprehensive 278-line W10 retro readout (`.claude/drafts/w10-retro-readout-bereket.md`) before retro skill ran — ahead-of-the-game discipline. Five new feedback primitives surfaced and saved as memories during the wave (multi-layer gap, refresh-before-status-claim 4-site application, integrity-claim independent verification, runtime-gate scoping, live-trace acceptance). Promoted to "named-primitive author" tier. |

### Child-Repo Teams — New Entries / Updates

#### noorinalabs-deploy team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aisha Idrissi (SRE) | 4 | **5** ↑ | W10 heavy lifter: 8 PRs (#150 Hetzner per-env, #157 CF stg, #155 promote, #168 auth→users, #175 bootstrap GHCR pull, #185 TF sensitive(), #177 B2 runbook, #189 BACKUP_B2_*). Drove Phase B fresh-start rebuild and captured 6 cloud-init/module hardening gaps in `deploy#173`. Sustained Section A delivery. |
| Lucas Ferreira (SRE) | 3 | **4** ↑ | 4 W10 PRs (alembic pre-deploy gate, verify-deploy split stg/prod, compose-validate paths + actionlint, integration-tests branch trigger fix). No CI-red merges this wave — W9 ding does not recur. Multiple tech-debt followups filed during reviews. |
| Weronika Zielinska (PA / Kafka) | 4 | 4 | 2 deploy PRs on kafka-kraft work + parent-repo design contribution. No change. |
| Nino Kavtaradze (Sec Eng) | 4 | 4 | Ongoing security enumeration patterns. No new wave-specific incident. No change. |

#### noorinalabs-user-service team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Anya Kowalczyk (TL) | 3 | **4** ↑ | Drove `user-service#80` alembic merge migration — load-bearing for deploy alembic pre-deploy gate. Tech-lead review depth scaled with the wave's cross-repo dependency requirements. |
| Mateo Salazar (Eng) | 4 | 4 | 2-3 W10 PRs (#83 Contract v6 image-tag, #87 GHCR PR Trivy trigger, #88 ci.yml deployments/** fix). Security-fixup-inline pattern continues. Same-file PR sequencing on `ghcr-publish.yml` (#83 + #87 on different branches) led to wave-merge conflict — minor process gap; tractably resolved. Holding at 4. |
| Idris Yusuf (Sec Eng) | 4 | 4 | No new wave-specific security incident. Holding at 4 from W9. |

#### noorinalabs-isnad-graph team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Idris Yusuf (Sec Eng — isnad-graph member) | — | **4** (new) | `isnad-graph#847` pip 26.0.1 → 26.1 CVE-2026-3219 with parallel cherry-pick `#850` to main — multi-branch security coverage handled correctly. Pip CVE bump landed twice (wave + main); merge-collapse worked cleanly. |
| Linh Pham (Frontend) | — | **3** (new) | `isnad-graph#844` Contract v6 image-tag emission. First W10 contribution; appropriate-scope. |

#### noorinalabs-landing-page team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| K. Mensah-Williams | — | **3** (new) | `landing-page#71` Contract v6 image-tag. First entry. Appropriate-scope. |

### Done Well / Needs Improvement (Phase 2 Wave 10)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Aisha Idrissi** (deploy SRE) | 8 PRs sustained across 7 days. Phase B fresh-start rebuild executed end-to-end. 6 hardening-gap items filed in `deploy#173`. | None this wave. |
| **Bereket Tadesse** (deploy Mgr) | Pre-retro 278-line readout. 5 named primitives saved as memories. | None this wave. |
| **Lucas Ferreira** (deploy SRE) | 4 clean PRs with no CI-red repeat from W9. Tech-debt-followup filing discipline. | None this wave. |
| **Anya Kowalczyk** (user-service TL) | Alembic merge migration #80 unblocked deploy alembic gate. Tech-lead review depth on cross-repo dependency. | None this wave. |
| **Mateo Salazar** (user-service Eng) | Multi-PR scope discipline; #87 PR-Trivy trigger added good defensive depth. | Same-file PR sequencing on `ghcr-publish.yml` led to wave-merge conflict; rebase-before-second-merge would have prevented. |
| **Idris Yusuf** (Sec Eng) | Pip CVE bump multi-branch coverage (#847 wave + #850 main cherry-pick) handled cleanly. | None this wave. |
| **Aino Virtanen** (SQL) | Hook 17 ship + charter updates. | None this wave. |
| **Nadia Khoury** (PD) | 5-repo wave-merge ceremony coordination + ghcr-publish.yml conflict resolution. | None this wave. |
| **Orchestrator** | Wave-wrapup ceremony executed end-to-end (ontology, annunaki, 45-worktree sweep, 5-repo wave-merge sequence, conflict resolution, retro). | Initial `git merge` on user-service local wave-10 was at a stale ref (3 behind origin); local-ref-staleness check before merge would have been cleaner. |


---

