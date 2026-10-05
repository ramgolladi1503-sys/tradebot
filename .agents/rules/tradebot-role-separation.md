# TradeBot Role Separation Rule

This rule is mandatory for all AI/human-assisted repository work.

## Roles

Recognized delivery roles:

- PRODUCT_OWNER
- BUSINESS_ANALYST
- SOLUTION_ARCHITECT
- SYSTEM_ARCHITECT
- QUANT_RESEARCH_ARCHITECT
- BACKEND_DEVELOPER
- DATA_QUANT_DEVELOPER
- INTEGRATION_DEVELOPER
- UI_DEVELOPER
- QA_ENGINEER
- SENIOR_QA
- UAT_REVIEWER
- RELEASE_MANAGER
- PRODUCTION_SRE

## Separation requirements

No role may approve its own deliverable.

Required examples:

- developers cannot emit `QA_PASSED`;
- QA cannot emit `PRODUCT_ACCEPTED`;
- architecture authors cannot self-certify implementation correctness;
- Release Manager cannot override failed mandatory gates;
- Product Owner cannot override failed CI/QA safety gates.

The same AI session may execute multiple roles sequentially only when:

1. each role's output is explicitly labeled;
2. role handoff evidence is preserved;
3. the later role independently reviews the earlier role output;
4. no required human-only approval is fabricated.

## Canonical workflow

All work follows `docs/tradebot_delivery/DELIVERY_LIFECYCLE.md` and `.agents/workflows/tradebot-delivery-orchestrator.md`.

The existing Hermes -> GSD safety pipeline remains mandatory inside the Architecture -> Development portion of this broader lifecycle.
