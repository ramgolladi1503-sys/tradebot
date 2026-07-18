import pytest
import sys
import subprocess

def test_verifier_importable():
    # Just checking it compiles
    import scripts.verify_opening_state_development_wfa
    assert True
