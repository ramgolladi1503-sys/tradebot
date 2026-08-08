CANDIDATE_HEAD: `b77638c4ae3d3d929dbe3798479b54f4e19d2c60`

PYTHON_VERSION: `Python 3.12.2`

COMMAND:

```bash
/opt/anaconda3/bin/python3 scripts/mros/calibrate_review_audit_board_v2.py --candidate-head b77638c4ae3d3d929dbe3798479b54f4e19d2c60
```

COMPLETE STDOUT:

```text
Traceback (most recent call last):
  File "/Users/madhuram/.mros-agent-bridge/jobs/mros-reviewer-R112-f7398869/scripts/mros/calibrate_review_audit_board_v2.py", line 89, in <module>
    if __name__=='__main__':raise SystemExit(main())
                                             ^^^^^^
  File "/Users/madhuram/.mros-agent-bridge/jobs/mros-reviewer-R112-f7398869/scripts/mros/calibrate_review_audit_board_v2.py", line 65, in main
    old='0'*40;oldr=dict(rg_auth);oldr['candidate_head']=old;olda=dict(ag_auth);olda['candidate_head']=old;oldn=dict(n);oldn['head']=old;seto('CAL-027',authz(oldr,olda,oldn,[])['advance'])
                                                                                                                                                        ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/madhuram/.mros-agent-bridge/jobs/mros-reviewer-R112-f7398869/scripts/mros/calibrate_review_audit_board_v2.py", line 64, in authz
    def authz(rv,av,nv,ctx):return authorize(sprint='S003',next_sprint='S004',candidate_head=head,review=rv,audit=av,native=nv,context_errors=ctx,review_manifest=rm,audit_manifest=am,queue_repo=q,review_manifest_path=rmp,audit_manifest_path=amp,review_round='R001',audit_round='A001',expected_native_ref=CALIBRATION_NATIVE_REF)
                                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/madhuram/.mros-agent-bridge/jobs/mros-reviewer-R112-f7398869/scripts/mros/advance_program.py", line 95, in authorize
    if not isinstance(review_round,str) or not re.fullmatch(r'R\d{3}',review_round):errors.append('REVIEW_ROUND_REQUIRED')
                                               ^^
UnboundLocalError: cannot access local variable 're' where it is not associated with a value
```

EXIT_CODE: `1`

RUNTIME_AUTHORITY=NONE

BROKER_ACTIONS=NONE

CALIBRATION_EXECUTION_RESULT=FAIL
