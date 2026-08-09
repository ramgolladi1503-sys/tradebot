#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

DEFAULT_SEAL='research/evidence/strategy_certification/SEALED_RESEARCH_CAMPAIGN_V1_SEAL.json'
DEFAULT_OUT='research/evidence/strategy_certification/SEALED_RESEARCH_CAMPAIGN_V1_POSTMORTEM.md'

def main(argv=None):
 ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');ap.add_argument('--seal',default=DEFAULT_SEAL);ap.add_argument('--output',default=DEFAULT_OUT);a=ap.parse_args(argv)
 root=Path(a.repo_root).resolve();sp=root/a.seal;out=root/a.output
 s=json.loads(sp.read_text())
 if s.get('status')!='CAMPAIGN_V1_SEALED_NO_EDGE':raise SystemExit('seal_not_terminal')
 lines=[
 '# Sealed Research Campaign V1 — Postmortem','',
 '**Terminal status:** `CAMPAIGN_V1_SEALED_NO_EDGE`','',
 'Research only. Runtime authority remains `NONE`. Broker actions remain prohibited. No edge is claimed.','',
 '## What the campaign established','',
 f"- Generations processed: **{s.get('generations_processed')}**.",
 f"- Frozen development configurations tested: **{s.get('total_frozen_configurations_tested')}**.",
 f"- Holdout accessed by any generation: **{'YES' if s.get('holdout_outcomes_accessed') else 'NO'}**.",
 '- No candidate established a defensible structural edge under the frozen campaign gates.','',
 '## Classes that failed to establish edge','',
 '- Temporal persistence/exhaustion and session-shape patterns.','- Opening drift, opening consensus, and opening dislocation patterns.','- Cross-market leader divergence, lag/catch-up, and relative-rank patterns.','- Intrabar range/volatility shock, compression, and reversal patterns.','- Rolling leader-agreement regime patterns.','',
 'These statements mean only that these tested, frozen formulations failed under this dataset and cost model. They do not prove the market contains no edge.','',
 '## Research lesson','',
 'Repeatedly changing OHLC thresholds after these failures would be data mining, not independent discovery. Development positives repeatedly failed untouched validation, so further search in the same information class has diminishing scientific value.','',
 '## Campaign V2 admission rule','',
 'Campaign V2 MUST NOT be opened merely to continue threshold search on the same synchronized OHLC/return feature space. It requires a materially new information class or a materially new causal research question frozen before outcomes are accessed.','',
 'Examples of admissible new information classes include:','',
 '- options-chain information such as IV, skew, term structure, OI/change-in-OI, and executable bid/ask where provenance is verified;','- order-book/depth or trade-flow information with timestamp and causality guarantees;','- independently sourced event/state features with predeclared timing and availability semantics.','',
 '## Prohibited continuation','',
 '- Do not resurrect V4–V10 nominees by relaxing minimum-trade gates.','- Do not reuse unopened holdout outcomes for hypothesis design.','- Do not spend the unused Campaign V1 configuration budget merely because it exists.','- Any future campaign must retain multiple-testing accounting across its own complete search family.','',
 '## Conclusion','',
 '**No structural edge was established. The campaign is closed as useful negative evidence.**',''
 ]
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text('\n'.join(lines),encoding='utf-8');print(out)
 return 0
if __name__=='__main__':raise SystemExit(main())
