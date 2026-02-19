PYTHON ?= python

.PHONY: setup test run-paper run-live sanity doctor

setup:
	$(PYTHON) -m pip install -r requirements.lock

test:
	PYTHONPATH=. $(PYTHON) -m pytest -q

run-paper:
	PYTHONPATH=. EXECUTION_MODE=PAPER $(PYTHON) main.py

run-live:
	PYTHONPATH=. EXECUTION_MODE=LIVE ALLOW_LIVE_PLACEMENT=true $(PYTHON) main.py

sanity:
	PYTHONPATH=. ./scripts/ci_sanity.sh

doctor:
	PYTHONPATH=. $(PYTHON) scripts/doctor.py
