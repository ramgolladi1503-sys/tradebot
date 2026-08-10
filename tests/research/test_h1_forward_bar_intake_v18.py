import os
import sys
import unittest
import tempfile
import pandas as pd

from scripts.research.hypothesis_factory.validate_h1_forward_bar_intake_v18 import validate_input_bars

class TestH1ForwardBarIntakeV18(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.obs_date = "2026-08-10"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_csv(self, rows, filename="test_bars.csv"):
        path = os.path.join(self.temp_dir.name, filename)
        header = "datetime,open,high,low,close,volume_optional,source,completed_bar,timezone\n"
        content = header + "\n".join(rows) + "\n"
        with open(path, "w") as f:
            f.write(content)
        return path

    def test_valid_completed_opening_bars_pass(self):
        rows = [
            "2026-08-10 09:15:00,24500.0,24530.0,24480.0,24510.0,0,KITE,true,Asia/Kolkata",
            "2026-08-10 09:20:00,24510.0,24540.0,24500.0,24525.0,0,KITE,true,Asia/Kolkata",
            "2026-08-10 09:25:00,24525.0,24550.0,24515.0,24540.0,0,KITE,true,Asia/Kolkata"
        ]
        csv_path = self._create_csv(rows)
        audit_path = os.path.join(self.temp_dir.name, "audit.json")
        res = validate_input_bars(csv_path, audit_path, self.obs_date)
        self.assertEqual(res["validation_verdict"], "FORWARD_BAR_INTAKE_VALID")
        self.assertEqual(res["bars_in_opening_window"], 3)
        self.assertEqual(res["orders_created"], 0)
        self.assertEqual(res["broker_writes_created"], 0)
        self.assertTrue(res["authority_flags_all_false"])

    def test_missing_required_column_fails(self):
        path = os.path.join(self.temp_dir.name, "missing_col.csv")
        with open(path, "w") as f:
            f.write("datetime,open,high,low,close\n2026-08-10 09:15:00,24500,24530,24480,24510\n")
        res = validate_input_bars(path, None, self.obs_date)
        self.assertEqual(res["validation_verdict"], "FORWARD_BAR_INTAKE_INVALID_SCHEMA")

    def test_duplicate_timestamp_fails(self):
        rows = [
            "2026-08-10 09:15:00,24500.0,24530.0,24480.0,24510.0,0,KITE,true,Asia/Kolkata",
            "2026-08-10 09:15:00,24500.0,24530.0,24480.0,24510.0,0,KITE,true,Asia/Kolkata"
        ]
        csv_path = self._create_csv(rows)
        res = validate_input_bars(csv_path, None, self.obs_date)
        self.assertEqual(res["validation_verdict"], "FORWARD_BAR_INTAKE_INVALID_DUPLICATES")

    def test_unsorted_timestamp_fails(self):
        rows = [
            "2026-08-10 09:20:00,24510.0,24540.0,24500.0,24525.0,0,KITE,true,Asia/Kolkata",
            "2026-08-10 09:15:00,24500.0,24530.0,24480.0,24510.0,0,KITE,true,Asia/Kolkata"
        ]
        csv_path = self._create_csv(rows)
        res = validate_input_bars(csv_path, None, self.obs_date)
        self.assertEqual(res["validation_verdict"], "FORWARD_BAR_INTAKE_INVALID_ORDERING")

    def test_non_5min_alignment_fails(self):
        rows = [
            "2026-08-10 09:17:00,24500.0,24530.0,24480.0,24510.0,0,KITE,true,Asia/Kolkata"
        ]
        csv_path = self._create_csv(rows)
        res = validate_input_bars(csv_path, None, self.obs_date)
        self.assertEqual(res["validation_verdict"], "FORWARD_BAR_INTAKE_INVALID_5MIN_ALIGNMENT")

    def test_non_5min_spacing_fails(self):
        rows = [
            "2026-08-10 09:15:00,24500.0,24530.0,24480.0,24510.0,0,KITE,true,Asia/Kolkata",
            "2026-08-10 09:25:00,24510.0,24540.0,24500.0,24525.0,0,KITE,true,Asia/Kolkata"
        ]
        csv_path = self._create_csv(rows)
        res = validate_input_bars(csv_path, None, self.obs_date)
        self.assertEqual(res["validation_verdict"], "FORWARD_BAR_INTAKE_INVALID_5MIN_SPACING")

    def test_no_opening_window_bars_fails(self):
        rows = [
            "2026-08-10 14:15:00,24500.0,24530.0,24480.0,24510.0,0,KITE,true,Asia/Kolkata"
        ]
        csv_path = self._create_csv(rows)
        res = validate_input_bars(csv_path, None, self.obs_date)
        self.assertEqual(res["validation_verdict"], "FORWARD_BAR_INTAKE_BLOCKED_NO_OPENING_BARS")

    def test_completed_bar_false_fails(self):
        rows = [
            "2026-08-10 09:15:00,24500.0,24530.0,24480.0,24510.0,0,KITE,false,Asia/Kolkata"
        ]
        csv_path = self._create_csv(rows)
        res = validate_input_bars(csv_path, None, self.obs_date)
        self.assertEqual(res["validation_verdict"], "FORWARD_BAR_INTAKE_INVALID_NOT_COMPLETED")

    def test_wrong_observation_date_fails(self):
        rows = [
            "2026-08-11 09:15:00,24500.0,24530.0,24480.0,24510.0,0,KITE,true,Asia/Kolkata"
        ]
        csv_path = self._create_csv(rows)
        res = validate_input_bars(csv_path, None, self.obs_date)
        self.assertEqual(res["validation_verdict"], "FORWARD_BAR_INTAKE_INVALID_OBSERVATION_DATE")

    def test_invalid_ohlc_high_below_close_fails(self):
        rows = [
            "2026-08-10 09:15:00,24500.0,24500.0,24480.0,24510.0,0,KITE,true,Asia/Kolkata"
        ]
        csv_path = self._create_csv(rows)
        res = validate_input_bars(csv_path, None, self.obs_date)
        self.assertEqual(res["validation_verdict"], "FORWARD_BAR_INTAKE_INVALID_OHLC")

    def test_invalid_ohlc_low_above_close_fails(self):
        rows = [
            "2026-08-10 09:15:00,24500.0,24530.0,24520.0,24510.0,0,KITE,true,Asia/Kolkata"
        ]
        csv_path = self._create_csv(rows)
        res = validate_input_bars(csv_path, None, self.obs_date)
        self.assertEqual(res["validation_verdict"], "FORWARD_BAR_INTAKE_INVALID_OHLC")

    def test_negative_price_fails(self):
        rows = [
            "2026-08-10 09:15:00,-24500.0,24530.0,24480.0,24510.0,0,KITE,true,Asia/Kolkata"
        ]
        csv_path = self._create_csv(rows)
        res = validate_input_bars(csv_path, None, self.obs_date)
        self.assertEqual(res["validation_verdict"], "FORWARD_BAR_INTAKE_INVALID_OHLC")

    def test_template_header_only(self):
        path = os.path.join(self.temp_dir.name, "header_only.csv")
        with open(path, "w") as f:
            f.write("datetime,open,high,low,close,volume_optional,source,completed_bar,timezone\n")
        res = validate_input_bars(path, None, self.obs_date)
        self.assertEqual(res["validation_verdict"], "FORWARD_BAR_INTAKE_BLOCKED_NO_INPUT")

    def test_no_order_or_broker_fields_required(self):
        rows = [
            "2026-08-10 09:15:00,24500.0,24530.0,24480.0,24510.0,0,KITE,true,Asia/Kolkata"
        ]
        csv_path = self._create_csv(rows)
        res = validate_input_bars(csv_path, None, self.obs_date)
        self.assertNotIn("order_id", res)
        self.assertNotIn("trade_id", res)
        self.assertEqual(res["orders_created"], 0)
        self.assertEqual(res["broker_writes_created"], 0)

if __name__ == "__main__":
    unittest.main()
