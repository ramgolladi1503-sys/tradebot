CANDIDATE_HEAD: `b77638c4ae3d3d929dbe3798479b54f4e19d2c60`

PYTHON_VERSION: `Python 3.12.2`

COMMAND:

```bash
python3 scripts/mros/calibrate_review_audit_board_v2.py --candidate-head b77638c4ae3d3d929dbe3798479b54f4e19d2c60
```

COMPLETE STDOUT:

```text
b77638c4ae3d3d929dbe3798479b54f4e19d2c60
Python 3.12.2
Traceback (most recent call last):
  File "/Users/madhuram/.mros-agent-bridge/jobs/mros-reviewer-R110-d5d4cbfa/scripts/mros/calibrate_review_audit_board_v2.py", line 89, in <module>
    if __name__=='__main__':raise SystemExit(main())
                                             ^^^^^^
  File "/Users/madhuram/.mros-agent-bridge/jobs/mros-reviewer-R110-d5d4cbfa/scripts/mros/calibrate_review_audit_board_v2.py", line 58, in main
    td,q,rmp,amp=_trusted_queue(head,rm,am,reviews,audits)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/madhuram/.mros-agent-bridge/jobs/mros-reviewer-R110-d5d4cbfa/scripts/mros/calibrate_review_audit_board_v2.py", line 24, in _trusted_queue
    td=tempfile.TemporaryDirectory(prefix='mros-cal-q-');q=Path(td.name);_git(q,'init');_git(q,'config','user.email','calibration@mros.local');_git(q,'config','user.name','MROS Calibration')
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/anaconda3/lib/python3.12/tempfile.py", line 882, in __init__
    self.name = mkdtemp(suffix, prefix, dir)
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/anaconda3/lib/python3.12/tempfile.py", line 373, in mkdtemp
    prefix, suffix, dir, output_type = _sanitize_params(prefix, prefix, dir)
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/anaconda3/lib/python3.12/tempfile.py", line 126, in _sanitize_params
    dir = gettempdir()
          ^^^^^^^^^^^^
  File "/opt/anaconda3/lib/python3.12/tempfile.py", line 315, in gettempdir
    return os.fsdecode(_gettempdir())
                       ^^^^^^^^^^^^^
  File "/opt/anaconda3/lib/python3.12/tempfile.py", line 308, in _gettempdir
    return _get_default_tempdir()
           ^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/anaconda3/lib/python3.12/tempfile.py", line 223, in _get_default_tempdir
    raise FileNotFoundError(_errno.ENOENT,
FileNotFoundError: [Errno 2] No usable temporary directory found in ['/var/folders/7h/d5fnr_sn43q_cxnd8vk1m2vm0000gn/T/', '/tmp', '/var/tmp', '/usr/tmp', '/Users/madhuram/.mros-agent-bridge/jobs/mros-reviewer-R110-d5d4cbfa']
```

EXIT_CODE: `1`

RUNTIME_AUTHORITY=NONE

BROKER_ACTIONS=NONE

CALIBRATION_EXECUTION_RESULT=FAIL