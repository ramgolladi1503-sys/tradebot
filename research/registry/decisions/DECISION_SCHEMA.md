# Decision Registry Schema

Each decision record must contain:

- Decision ID
- Version
- Decision type: promote / hold / demote / reject / invalidate / supersede / governance
- Linked Claim ID(s)
- Source lifecycle state
- Destination lifecycle state, if applicable
- Evidence IDs considered
- Calibration IDs considered
- Attack artifacts considered
- Decision rationale
- Dissent or unresolved concerns
- Known weaknesses accepted
- Review triggers
- Effective timestamp
- Decision authority / reviewer
- Supersession links, if applicable

A decision record does not create evidence. It records how existing registered evidence changed claim authority.
