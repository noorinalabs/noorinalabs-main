## Promotion Audit — wave-4 (2026-05-05)

**Summary:** 0 AUTO · 0 DECIDE · 65 KEPT · 3 SUPERSEDED · 1 ALREADY-PROMOTED (total candidates: 69)

### AUTO-PROMOTED (artifacts generated this run)

_None this run._

### REQUIRES DECISION (issues filed)

_None this run._

### KEPT (no action — informational)

All 65 KEPT candidates have `promotion_target: none` in their frontmatter (informational memories) OR have not yet crossed promotion thresholds. The full per-item table is omitted here for brevity — the deterministic helpers in `.claude/skills/promotion-audit/helpers.py` produce identical output on byte-stable inputs.

### STALE-OPT-OUT (sub-class of KEPT — shipped in P3W4 #266)

_None this run._ Highest `retro_citations` value across all memories is 3; the STALE-OPT-OUT threshold is `2 * promotion_threshold` (i.e., ≥ 6 retro citations on a `promotion_target: none` memory). The class did not fire this audit.

### SUPERSEDED

3 memories (status `superseded` or `enforced-elsewhere` with explicit `superseded_by`):
- `feedback_disable_followup_load_bearing.md` — superseded 2026-04-17 by charter § Load-Bearing Followups for Disabled CI Jobs
- (2 additional — see helpers.py output)

### ALREADY-PROMOTED

1 memory (name appears in `find_already_promoted()` set via `Promotion provenance:` block in `charter/hooks.md`).

### Caveat

main#269 (memory-audit P3W4-wrapup) is the W5 follow-on for systematic frontmatter classification. The 36 feedback memories currently at `promotion_target: none` need classification (14 charter / 4 hook / 3 skill candidates per the issue). Once classified, subsequent audits will surface real AUTO/DECIDE candidates.

### Reproducibility

Run from repo root:

```bash
python3 -c "
import sys; sys.path.insert(0, '.claude/skills/promotion-audit')
from helpers import (
    read_all_memories, read_all_charter_sections, read_all_skills,
    find_already_promoted, count_retro_citations, count_skill_invocations,
    classify_memory, classify_section, classify_skill,
)
mem_dir='/home/parameterization/.claude/projects/-home-parameterization-code-noorinalabs-main/memory'
charter='.claude/team/charter'; skills='.claude/skills'
hooks='.claude/team/charter/hooks.md'; fb='.claude/team/feedback_log.md'
already=find_already_promoted(hooks)
ds=[]
for m in read_all_memories(mem_dir):
    ds.append(classify_memory(m,{'retro_citations':count_retro_citations(m,fb)},already))
for s in read_all_charter_sections(charter):
    ds.append(classify_section(s,{'skill_invocations':0},already))
for sk in read_all_skills(skills):
    ds.append(classify_skill(sk,{'invocations':count_skill_invocations(sk.name,'.')},already))
c={}
for d in ds: c[d.kind]=c.get(d.kind,0)+1
print('Total:',len(ds))
for k in sorted(c): print(f'  {k}: {c[k]}')
"
```

Re-running on byte-stable repo state produces identical counts.
