#!/usr/bin/env python3
"""Machine-readable MROS v1.0 program catalog through M8."""
from __future__ import annotations
from dataclasses import dataclass
PHASES={1:("CONTRACT_DESIGN_FREEZE","Define scope, interfaces, invariants, schemas, dependencies, risks, and evidence obligations before implementation."),2:("CORE_IMPLEMENTATION","Implement the smallest production-quality capability that satisfies the frozen contract without adding adjacent scope."),3:("INTEGRATION_NEGATIVE_CONTROLS","Integrate immediate dependencies and prove invalid, missing, stale, contradictory, duplicate, and unauthorized inputs fail safely."),4:("VERIFICATION_CALIBRATION_INDEPENDENT_ATTACK","Run evidence-driven QA, adversarial review, reproducibility checks, and calibration/robustness tests appropriate to the work package."),0:("ACCEPTANCE_EVIDENCE_SEAL_HANDOFF","Seal artifacts, verify acceptance criteria, record decisions/limitations, update durable knowledge, and prepare the next sprint without expanding scope.")}
WPS={
1:("M1","Research Constitution","Establish immutable research principles, knowledge classes, burden-of-proof rules, no-drift controls, and evidence-first behavior.","A versioned constitution defining what may be claimed, uncertainty semantics, and non-bypassable rules.","Constitution ambiguity, conflicting rules, unenforceable language"),
2:("M1","Governance & Authority Model","Define authority grades, promotion gates, review roles, independence requirements, escalation paths, and exceptions policy.","An authority model preventing discovering agents from granting final authority to their own result.","Grade inflation, circular approval, self-certification"),
3:("M1","Research Registries & Identity","Create canonical identity schemes and schemas for claims, experiments, datasets, evidence, calibration, and decisions.","Machine-readable registry contracts with immutable IDs and referential integrity.","Orphan evidence, mutable identity, schema drift"),
4:("M1","Decision Ledger & Supersession","Record why major decisions were made and how later evidence changes or supersedes them without deleting history.","Append-only decision and supersession model with review triggers.","Silent reversals, lost rationale, conflicting active decisions"),
5:("M1","Research Knowledge Graph","Define relationships among datasets, experiments, evidence, claims, calibration, attacks, and decisions.","A queryable knowledge model answering why a claim is believed and what invalidates it.","Circular support, missing lineage, stale graph edges"),
6:("M1","MROS Bible & Research Journal","Create the durable operating manual and chronological research journal, versioned alongside code.","A living handbook plus append-only journal separating stable rules from historical learning.","Documentation drift, stale instructions, chat-only knowledge"),
7:("M2","Certifier Calibration Framework","Build the harness that evaluates the certifier as an instrument before unknown-market conclusions are trusted.","A deterministic calibration framework with frozen development-only inputs and zero promotion authority.","Calibration contaminates holdout or changes official results"),
8:("M2","Synthetic Edge Generator","Inject known effects into controlled development copies to measure detection probability across effect size, frequency, variance, and sample size.","A planted-edge laboratory producing power curves.","Injection leakage, unrealistic synthetic structure, hidden mutation"),
9:("M2","Null World Generator","Generate dependency-preserving null worlds to measure false discovery behavior under no-edge conditions.","A null simulator supporting time-series-appropriate permutation/block/bootstrap schemes.","Broken dependence, overly easy nulls, leakage of true structure"),
10:("M2","Representation Audit","Test whether the certifier's observable representation can express plausible mechanisms and whether conclusions are representation-bound.","A representation coverage matrix and outcome-blind alternative state encodings.","Representation tuning to outcomes, hidden hypothesis inflation"),
11:("M2","Gate Attribution","Quantify exactly which gates remove candidates and whether gate semantics match the claim being tested.","A full attrition ledger from raw effect through statistical and robustness gates.","Semantic mismatch, double penalties, untraceable rejection"),
12:("M2","Statistical Power & Multiplicity","Measure sensitivity, specificity, detectable effect sizes, dependency-adjusted multiplicity, and uncertainty of the certifier.","A calibrated operating-characteristic report for the full certification pipeline.","Overclaiming exhaustion or mishandling correlated tests"),
13:("M3","Information Discovery Engine Core","Build the engine that measures predictive information before strategy construction.","A causal-time-safe information scoring pipeline with chronological validation and incremental information analysis.","Leakage, estimator bias, unstable rankings"),
14:("M3","Signal Registry & Feature Authority","Register every observable with definition, provenance, timestamp semantics, allowed transformations, and information authority.","A canonical signal catalog preventing ambiguous or duplicated feature definitions.","Feature aliases, timestamp ambiguity, silent recalculation"),
15:("M3","Information Graph & Lead/Lag","Map stable information transfer among indices, constituents, futures, options, and microstructure observables.","A time-directed information graph with strength, delay, decay, regime stability, and uncertainty.","Spurious causality, common-driver confounding, temporal aggregation artifacts"),
16:("M4","Mechanism Discovery Engine Core","Translate high-information relationships into explicit market-process explanations and falsifiable predictions.","A mechanism engine separating economic process from surface pattern.","Storytelling after the fact, non-falsifiable mechanisms"),
17:("M4","Mechanism Registry & Market Process Graph","Persist mechanism contracts, dependencies, evidence, competing explanations, and lifecycle status.","A registry preserving supported, rejected, and unresolved mechanisms.","Narrative duplication, causal cycles, lost rejected work"),
18:("M5","Hypothesis Factory","Convert registered mechanisms into bounded, predeclared, outcome-blind experimental contracts.","A hypothesis generator producing testable claims rather than parameter soup.","Outcome-driven invention, cosmetic hypothesis multiplication"),
19:("M5","Hypothesis Scheduler & Search Budget","Control experiment order, global search budget, family budgets, multiplicity denominator, and sealed-tail access.","A scheduling authority preventing reset-and-retry research loops.","p-hacking through campaign resets, denominator laundering"),
20:("M6","Scientific Certification Engine","Run calibrated scientific gates with replication, robustness, independent attack, and sealed-holdout discipline.","A certification pipeline promoting only claims surviving calibrated attacks.","Certifier used outside calibrated domain, manual overrides"),
21:("M7","Economic Certification Engine","Translate scientific effects into executable economics using realistic market microstructure and capacity assumptions.","An execution-aware certification layer separated from predictive/statistical authority.","LTP-as-fill, optimistic slippage, hidden liquidity assumptions"),
22:("M8","Knowledge Promotion & Confidence Passport","Promote certified outputs into institutional knowledge with explicit authority, limitations, review triggers, and supersession.","A durable confidence passport for every accepted claim.","Stale operational knowledge, grade without evidence")}
WP_ACCEPTANCE={
1:["Constitution can be applied to three historical examples without ambiguity.","No rule permits promotion without new evidence.","Independent reviewer can classify sample statements consistently."],
2:["Each authority grade has objective minimum evidence.","Promotion requires explicit gate evidence.","Exceptions are logged and cannot grant higher authority than evidence supports."],
3:["All registered objects validate against schema.","Broken references are detected.","IDs are unique and never reused.","Required provenance cannot be omitted."],
4:["Historical decisions remain reproducible.","Supersession never erases original evidence.","Current authority can be computed from the ledger."],
5:["Claim-to-evidence lineage is complete.","Dataset invalidation impact can be traced.","Cycles implying circular evidence are detectable."],
6:["A new agent can orient using repository only.","Stable rules and chronological history are not mixed.","Every milestone release updates manual and journal."],
7:["Same inputs reproduce the same calibration.","Calibration cannot promote strategies.","Sealed holdouts are inaccessible by design."],
8:["Known edges are injected exactly as specified.","Original data remain unchanged.","Recovery probability is measured with confidence intervals."],
9:["Null generator removes predictive relation without corrupting marginal structure.","False positive rates are quantified.","Null worlds are reproducible."],
10:["Representation changes are outcome-blind.","Coverage gaps are documented.","No failed hypothesis is rescued by post-hoc encoding."],
11:["Every rejection has a machine-readable reason.","Statistical null matches the stated claim.","Diagnostic alternatives never silently replace official gates."],
12:["Minimum detectable effects are published.","Calibration uncertainty is quantified.","No absence-of-edge claim exceeds demonstrated power."],
13:["No future information is used in features.","Scores reproduce across runs.","Incremental information is measured against declared baselines."],
14:["Duplicate semantics are detected.","Every signal is causally timestamped.","Unavailable future-state fields cannot be registered as predictors."],
15:["Edges survive chronological replication.","Directionality is not inferred from contemporaneous correlation alone.","Unstable edges are not promoted."],
16:["Every mechanism has a causal sequence and destroyers.","Mechanism formulation does not rely on future outcomes.","Alternative explanations are recorded."],
17:["Mechanisms can be compared without prose ambiguity.","Rejected mechanisms remain queryable.","Process graph has explicit temporal direction."],
18:["Hypothesis is frozen before outcomes attach.","Threshold variants count against the same family budget.","Mechanism linkage is mandatory."],
19:["Failed tests remain in the denominator.","No new campaign resets multiplicity without new information authority.","Holdout cannot be reopened after failure."],
20:["All required scientific gates pass for certification.","Calibration coverage includes the tested effect region.","Attack artifacts exist.","Failure remains authoritative."],
21:["Entry and exit prices are executable or conservatively modeled.","Sensitivity to costs is published.","Capacity and liquidity constraints are explicit."],
22:["No claim becomes operational without a complete passport.","Review triggers are machine-readable.","Downgrade and supersession preserve history."]}
MILESTONE_LAST_SPRINT={"M1":30,"M2":60,"M3":75,"M4":85,"M5":95,"M6":100,"M7":105,"M8":110}
@dataclass(frozen=True)
class SprintSpec:
 sprint:str;number:int;wp:str;wp_number:int;milestone:str;phase:str;objective:str;product_context:str;primary_risk:str;assurance_tier:str;terminal_m8:bool

def sprint_spec(number:int)->SprintSpec:
 if number<1 or number>110:raise ValueError("AUTONOMOUS_PROGRAM_BOUNDARY_S001_TO_S110")
 wp=((number-1)//5)+1
 if wp not in WPS:raise ValueError("WORK_PACKAGE_NOT_IN_M1_M8")
 milestone,_,_,product,risk=WPS[wp];phase,phase_obj=PHASES[number%5];tier="FULL" if MILESTONE_LAST_SPRINT[milestone]==number else "NORMAL"
 return SprintSpec(f"S{number:03d}",number,f"WP{wp:03d}",wp,milestone,phase,phase_obj,product,risk,tier,number==110)
def next_sprint(number:int)->str|None:return None if number>=110 else f"S{number+1:03d}"
def common_acceptance()->list[str]:return ["All sprint tasks are implemented or explicitly rejected with evidence.","No out-of-scope files or behavior changes are present.","All required tests pass; expected negative tests fail for the correct reason.","Evidence is reproducible by an independent session from documented commands.","No Critical or High research-integrity defect remains open.","Authority/status language exactly matches the evidence produced.","Exact branch/commit, changed-file manifest, test outputs, artifact IDs/hashes, assumptions/unknowns, independent attack notes, and sprint decision are recorded."]
def sprint_acceptance(number:int)->list[str]:
 s=sprint_spec(number);items=list(common_acceptance())
 if number%5==0:items.extend(WP_ACCEPTANCE[s.wp_number])
 if number in MILESTONE_LAST_SPRINT.values():items.extend(["All work packages in the milestone are accepted.","Milestone evidence manifest is sealed and reviewable.","Manual and research journal are updated for milestone release."])
 return items
