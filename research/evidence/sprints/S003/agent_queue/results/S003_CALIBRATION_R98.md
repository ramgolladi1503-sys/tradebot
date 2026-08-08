CANDIDATE_HEAD
`c1a4ab07daf19db636c6ea8b0d951c642808d32e`

PYTHON_VERSION
`Python 3.12.2`

COMMAND
`python3 scripts/mros/calibrate_review_audit_board.py`

STDOUT

```text
Traceback (most recent call last):
  File "/Users/madhuram/.mros-agent-bridge/jobs/mros-reviewer-R98-c6f348dc/scripts/mros/calibrate_review_audit_board.py", line 226, in <module>
    raise SystemExit(main())
                     ^^^^^^
  File "/Users/madhuram/.mros-agent-bridge/jobs/mros-reviewer-R98-c6f348dc/scripts/mros/calibrate_review_audit_board.py", line 146, in main
    with tempfile.TemporaryDirectory(prefix="mros-board-cal-") as td:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/anaconda3/lib/python3.12/tempfile.py", line 882, in __init__
    self.name = mkdtemp(suffix, prefix, dir)
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/anaconda3/lib/python3.12/tempfile.py", line 373, in mkdtemp
    prefix, suffix, dir, output_type = _sanitize_params(prefix, suffix, dir)
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/anaconda3/lib/python3.12/tempfile.py", line 126, in _sanitize_params
    dir = gettempdir()
          ^^^^^^^^^^^^
  File "/opt/anaconda3/lib/python3.12/tempfile.py", line 315, in gettempdir
    return _os.fsdecode(_gettempdir())
                        ^^^^^^^^^^^^^
  File "/opt/anaconda3/lib/python3.12/tempfile.py", line 308, in _gettempdir
    tempdir = _get_default_tempdir()
              ^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/anaconda3/lib/python3.12/tempfile.py", line 223, in _get_default_tempdir
    raise FileNotFoundError(errno.ENOENT, "No usable temporary directory found in %s" % dirlist)
FileNotFoundError: [Errno 2] No usable temporary directory found in ['/var/folders/7h/d5fnr_sn43q_cxnd8vk1m2vm0000gn/T/', '/tmp', '/var/tmp', '/usr/tmp', '/Users/madhuram/.mros-agent-bridge/jobs/mros-reviewer-R98-c6f348dc']
```

EXIT_CODE
`1`

RUNTIME_AUTHORITY=NONE

BROKER_ACTIONS=NONE

CALIBRATION_EXECUTION_RESULT=FAIL