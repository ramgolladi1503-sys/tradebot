import pytest
from pathlib import Path
from core.upstox_capture.lifecycle_ledger import LifecycleLedger
from core.upstox_capture.raw_writer import RawWriter

def test_lifecycle_ledger_contract(tmp_path):
    # Ensure it accepts an output_dir and creates the lifecycle path correctly
    output_dir = tmp_path / "lifecycle"
    ledger = LifecycleLedger(output_dir)
    
    # Ensure it has the generic log_event method
    ledger.log_event("TEST_EVENT", {"foo": "bar"})
    
    assert (output_dir / "session_lifecycle.jsonl").exists()

def test_raw_writer_contract(tmp_path):
    # Ensure RawWriter accepts output_dir and connection_id
    writer = RawWriter(tmp_path, connection_id="conn_active")
    
    # Ensure write_frame accepts the correct parameters
    test_bytes = b"test_frame_data"
    writer.write_frame(test_bytes, message_class="FeedResponse", decode_success=True)
    
    assert writer.current_bytes_written > 0
    assert len(writer.index_records) > 0
