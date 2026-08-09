MROS S003 deterministic calibration R121

- Candidate HEAD: `2c0174b4becfc06a5db090d59944375693126ba1`
- Python: `/opt/anaconda3/lib/python3.12`
- Command:
  `/opt/anaconda3/bin/python3 scripts/mros/calibrate_review_audit_board_v2.py --candidate-head 2c0174b4becfc06a5db090d59944375693126ba1`
- Exit code: `1`
- Runtime authority: `NONE`
- Broker actions: `NONE`

Stdout:

```text
<empty>
```

Stderr:

```text
Traceback (most recent call last):
  File "/Users/madhuram/.mros-agent-bridge/jobs/mros-reviewer-R121-ea4acfb7/scripts/mros/calibrate_review_audit_board_v2.py", line 103, in <module>
    if __name__=='__main__':raise SystemExit(main())
                                             ^^^^^^
  File "/Users/madhuram/.mros-agent-bridge/jobs/mros-reviewer-R121-ea4acfb7/scripts/mros/calibrate_review_audit_board_v2.py", line 65, in main
    td,q,rmp,amp=_trusted_queue(head,rm,am,reviews,audits)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/madhuram/.mros-agent-bridge/jobs/mros-reviewer-R121-ea4acfb7/scripts/mros/calibrate_review_audit_board_v2.py", line 24, in _trusted_queue
    td=tempfile.TemporaryDirectory(prefix='mros-cal-q-');q=Path(td.name);_git(q,'init');_git(q,'config','user.email','calibration@mros.local');_git(q,'config','user.name','MROS Calibration')
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/anaconda3/lib/python3.12/tempfile.py", line 882, in __init__
    self.name = mkdtemp(suffix, prefix, dir)
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/anaconda3/lib/python3.12/tempfile.py", line 373, in mkdtemp
    prefix, suffix, dir, output_type = _sanitize_params(prefix, suffix, dir)
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/anaconda3/lib/python3.12/tempfile.py", line 126, in _sanitize_params
    dir = gettempdir()
          ^^^^^^^^^^^^
  File "/opt/anaconda3/lib/python3.12/tempfile.py", line 315, in gettempdir
    tempdir = _get_default_tempdir()
             ^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/anaconda3/lib/python3.12/tempfile.py", line 223, in _get_default_tempdir
    raise FileNotFoundError(errno.ENOENT, "No usable temporary directory found in %s" % dirlist)
FileNotFoundError: [Errno 2] No usable temporary directory found in ['/var/folders/7h/d5fnr_sn43q_cxnd8vk1m2vm0000gn/T/', '/tmp', '/var/tmp', '/usr/tmp', '/Users/madhuram/.mros-agent-bridge/jobs/mros-reviewer-R121-ea4acfb7']
```

Final calibration verdict: `NOT PRODUCED — calibration blocked before verdict generation because no writable temporary directory was available.`