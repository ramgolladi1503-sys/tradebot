import os
from pathlib import Path

def test_hygiene_no_early_returns_in_tests():
    tests_dir = Path(__file__).parent
    for py_file in tests_dir.glob("test_*.py"):
        content = py_file.read_text()
        
        # Check for early returns (return immediately after def)
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if line.strip().startswith('def test_'):
                if i + 1 < len(lines) and lines[i+1].strip() == 'return':
                    assert False, f"Found early return in {py_file.name} at line {i+2}"
                    
        # Check for '# removed' replacing assertions
        if "# " + "removed" in content and "test_hygiene.py" not in py_file.name:
            assert False, f"Found '# removed' in {py_file.name}, indicating weakened assertions."

def test_hygiene_advisory_rejection_present():
    tests_dir = Path(__file__).parent
    
    # test_candidate_generator_contract.py must contain ADVISORY test
    contract_test = tests_dir / "test_candidate_generator_contract.py"
    if contract_test.exists():
        assert "def test_audit_advisory_not_executable" in contract_test.read_text()
        
    # test_candidate_to_signal_adapter.py must check ADVISORY rejection
    adapter_test = tests_dir / "test_candidate_to_signal_adapter.py"
    if adapter_test.exists():
        assert "ADVISORY" in adapter_test.read_text()
