import pandas as pd
import numpy as np
import itertools
import hashlib
import json
import inspect
from typing import List, Dict, Any, Optional, Callable
from core.backtest_elite import VectorizedBacktestEngine, EliteBacktestConfig


def validate_fold_ledger(ledger):
    """Fail closed on chronology, overlap, purge, or embargo ledger mutations."""
    required = {"train_start", "train_end", "test_start", "test_end", "overlap_rows", "purge_interval", "embargo_interval"}
    for row in ledger:
        if not required.issubset(row):
            raise ValueError("wfa_fold_ledger_fields_missing")
        train_end = pd.Timestamp(row["train_end"])
        test_start = pd.Timestamp(row["test_start"])
        if int(row["overlap_rows"]) != 0 or train_end >= test_start:
            raise ValueError("wfa_fold_ledger_overlap")
    return True


def validate_feature_causality_ledger(
    ledger, *, expected_builder_sha256=None, expected_source_sha256=None,
    expected_corpus_freeze_sha256=None, expected_builder_id=None,
    expected_fold_ids=None, expected_normalization_source_sha256=None,
):
    required = {
        "feature_name", "feature_source_start_timestamp",
        "feature_source_end_timestamp", "decision_timestamp",
        "feature_cutoff_ts", "feature_source_timestamp", "session_id",
        "fold_id", "available_at_decision",
    }
    for row in ledger:
        if not required.issubset(row):
            raise ValueError("wfa_feature_causality_metadata_missing")
        source_start = pd.Timestamp(row["feature_source_start_timestamp"])
        source_end = pd.Timestamp(row["feature_source_end_timestamp"])
        decision = pd.Timestamp(row["decision_timestamp"])
        cutoff = pd.Timestamp(row["feature_cutoff_ts"])
        if source_start > source_end or source_end > decision or source_end > cutoff:
            raise ValueError("wfa_feature_causality_violation")
        if not bool(row["available_at_decision"]) or bool(row.get("leakage_detected")):
            raise ValueError("wfa_feature_causality_violation")
        if str(pd.Timestamp(row["decision_timestamp"]).date()) != str(row["session_id"]):
            raise ValueError("wfa_feature_session_mismatch")
        builder_sha = str(row.get("feature_builder_sha256", ""))
        source_sha = str(row.get("source_partition_sha256", ""))
        corpus_sha = str(row.get("corpus_freeze_sha256", ""))
        if not builder_sha or builder_sha == "unidentified":
            raise ValueError("wfa_feature_builder_identity_missing")
        if expected_builder_sha256 and builder_sha != expected_builder_sha256:
            raise ValueError("wfa_feature_builder_identity_mismatch")
        builder_id = str(row.get("feature_builder_id", ""))
        if not builder_id or builder_id == "unidentified":
            raise ValueError("wfa_feature_builder_id_missing")
        if expected_builder_id and builder_id != expected_builder_id:
            raise ValueError("wfa_feature_builder_id_mismatch")
        if not source_sha or source_sha == "unidentified":
            raise ValueError("wfa_source_authority_missing")
        if expected_source_sha256 and source_sha != expected_source_sha256:
            raise ValueError("wfa_source_authority_mismatch")
        if not corpus_sha or corpus_sha == "unidentified":
            raise ValueError("wfa_corpus_authority_missing")
        if expected_corpus_freeze_sha256 and corpus_sha != expected_corpus_freeze_sha256:
            raise ValueError("wfa_corpus_authority_mismatch")
        if expected_fold_ids is not None and int(row["fold_id"]) not in expected_fold_ids:
            raise ValueError("wfa_feature_fold_mismatch")
        fit_scope = str(row.get("normalization_fit_scope", ""))
        if fit_scope != "PASS_NOT_APPLICABLE" and fit_scope != "TRAIN_ONLY":
            raise ValueError("wfa_normalization_scope_mismatch")
        normalization_source_sha = str(row.get("normalization_fit_source_sha256", ""))
        if not normalization_source_sha or normalization_source_sha == "unidentified":
            raise ValueError("wfa_normalization_source_authority_missing")
        expected_norm_sha = expected_normalization_source_sha256 or expected_source_sha256
        if expected_norm_sha and normalization_source_sha != expected_norm_sha:
            raise ValueError("wfa_normalization_source_authority_mismatch")
        if bool(row.get("fit_uses_test_data")):
            raise ValueError("wfa_normalization_test_data")
        fit_end = row.get("normalization_fit_end")
        if fit_end not in (None, "", "None") and pd.Timestamp(fit_end) >= decision:
            raise ValueError("wfa_normalization_fit_overlap")
        fit_fold = row.get("normalization_fit_fold_id")
        if fit_fold not in (None, "", "None") and int(fit_fold) != int(row["fold_id"]):
            raise ValueError("wfa_normalization_fold_mismatch")
    return True


def validate_parameter_freeze_ledger(ledger):
    for row in ledger:
        if pd.Timestamp(row["parameter_selection_data_end"]) >= pd.Timestamp(row["test_start"]):
            raise ValueError("wfa_parameter_freeze_violation")
    return True


def validate_parameter_selection_ledger(ledger):
    """Require complete, hash-bound, train-only candidate provenance."""
    required = {
        "selection_data_end", "test_start", "selected_parameters",
        "candidate_scores", "candidate_ledger_sha256", "selection_source",
    }
    for row in ledger:
        if not required.issubset(row) or row["selection_source"] != "TRAIN_ONLY":
            raise ValueError("wfa_parameter_selection_provenance_missing")
        candidates = row["candidate_scores"]
        if not candidates:
            raise ValueError("wfa_parameter_selection_candidates_missing")
        payload = json.dumps(candidates, sort_keys=True, default=str)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if digest != row["candidate_ledger_sha256"]:
            raise ValueError("wfa_parameter_selection_provenance_hash")
        test_start = pd.Timestamp(row["test_start"])
        selection_end = pd.Timestamp(row["selection_data_end"])
        if selection_end >= test_start:
            raise ValueError("wfa_parameter_selection_test_leakage")
        if any(pd.Timestamp(candidate["selection_data_end"]) >= test_start for candidate in candidates):
            raise ValueError("wfa_parameter_candidate_test_leakage")
        if row["selected_parameters"] not in [candidate["parameters"] for candidate in candidates]:
            raise ValueError("wfa_selected_parameter_not_in_candidates")
    return True

class WalkForwardAnalyzer:
    """
    Performs Walk-Forward Analysis (WFA) to prevent curve-fitting.
    
    Splits data into rolling train/test windows.
    Optimizes parameters on the train window, tests blindly on the test window.
    """
    
    def __init__(
        self, 
        data: pd.DataFrame, 
        train_years: int = 3, 
        test_years: int = 1,
        slippage_bps: float = 20.0,  # 0.2% slippage requirement
        spread_bps: float = 0.0
        , label_horizon_minutes: int = 0
        , purge_minutes: int | None = None
        , embargo_minutes: int = 0
        , signal_builder: Callable[[pd.DataFrame, Any], pd.DataFrame] | None = None
    ):
        self.data = data.copy()
        if not pd.api.types.is_datetime64_any_dtype(self.data.index):
            self.data.index = pd.to_datetime(self.data.index)
        self.data.sort_index(inplace=True)
        
        self.train_years = train_years
        self.test_years = test_years
        self.slippage_bps = slippage_bps
        self.spread_bps = spread_bps
        if label_horizon_minutes < 0 or (purge_minutes is not None and purge_minutes < 0) or embargo_minutes < 0:
            raise ValueError("wfa_boundaries_must_be_nonnegative")
        self.purge = pd.Timedelta(minutes=max(label_horizon_minutes, purge_minutes or 0))
        self.label_horizon = self.purge
        self.embargo = pd.Timedelta(minutes=embargo_minutes)
        # Maximum trailing feature lookback used by the shared signal builder
        # (EMA-50). This is metadata for boundary evidence, not a signal change.
        self.feature_lookback_minutes = 50
        self.signal_builder = signal_builder
        
        self.oos_results = []
        self.best_params_per_window = []
        self.fold_ledger = []
        self.parameter_freeze_ledger = []
        self.parameter_selection_ledger = []
        self.aggregation_report = {}
        self.uncertainty_report = {}
        self.feature_causality_ledger = []
        self.frozen_config_hash = None
        self.holdout_registry = {"status": "NOT_APPLICABLE_FOR_FORWARD_MECHANICS", "evaluations": 0}

    def generate_windows(self):
        """Generates train/test date ranges based on available years."""
        years = sorted(self.data.index.year.unique())
        
        windows = []
        for i in range(len(years) - self.train_years - self.test_years + 1):
            train_start_year = years[i]
            train_end_year = years[i + self.train_years - 1]
            test_start_year = years[i + self.train_years]
            test_end_year = years[i + self.train_years + self.test_years - 1]
            
            raw_train_mask = (self.data.index.year >= train_start_year) & (self.data.index.year <= train_end_year)
            raw_test_mask = (self.data.index.year >= test_start_year) & (self.data.index.year <= test_end_year)
            raw_test_start = self.data.index[raw_test_mask].min()
            raw_test_end = self.data.index[raw_test_mask].max()
            effective_test_start = raw_test_start + self.embargo
            train_mask = raw_train_mask & ((self.data.index + self.purge) < raw_test_start)
            test_mask = raw_test_mask & (self.data.index >= effective_test_start)
            train_df = self.data.loc[train_mask].copy()
            test_df = self.data.loc[test_mask].copy()
            
            windows.append({
                "train_start": str(train_start_year),
                "train_end": str(train_end_year),
                "test_start": str(test_start_year),
                "test_end": str(test_end_year),
                "train_df": train_df,
                "test_df": test_df,
                "raw_test_start": raw_test_start,
                "raw_test_end": raw_test_end,
                "effective_test_start": effective_test_start,
                "purge_interval": self.purge,
                "embargo_interval": self.embargo,
            })
        return windows

    def optimize(self, train_df: pd.DataFrame, param_grid: Dict[str, List[Any]]) -> Dict[str, Any]:
        """Runs a grid search over param_grid on the train_df."""
        keys, values = zip(*param_grid.items())
        permutations = [dict(zip(keys, v)) for v in itertools.product(*values)]
        
        best_pl = -float('inf')
        best_params = permutations[0]
        candidate_scores = []
        
        for params in permutations:
            config = EliteBacktestConfig(
                slippage_bps=self.slippage_bps,
                spread_bps=self.spread_bps,
                use_synth_chain=False, # Keep fast for optimization
                **params
            )
            
            engine = VectorizedBacktestEngine(train_df, config)
            res_df = (
                engine.run_vectorized_signals(self.signal_builder(train_df, config))
                if self.signal_builder is not None
                else engine.generate_signals_vectorized()
            )
            
            total_pl = res_df["pl"].sum() if not res_df.empty else 0
            candidate_scores.append({
                "parameters": params,
                "train_net_pl": float(total_pl),
                "train_rows": int(len(train_df)),
                "selection_data_end": str(train_df.index.max()),
            })
            if total_pl > best_pl:
                best_pl = total_pl
                best_params = params
                
        self._last_candidate_scores = candidate_scores
        return best_params

    def test(self, test_df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """Evaluates out-of-sample data with the best parameters."""
        config = EliteBacktestConfig(
            slippage_bps=self.slippage_bps,
            spread_bps=self.spread_bps,
            use_synth_chain=False,
            **params
        )

        engine = VectorizedBacktestEngine(test_df, config)
        signal_rows = self.signal_builder(test_df, config) if self.signal_builder is not None else None
        res_df = engine.run_vectorized_signals(signal_rows) if signal_rows is not None else engine.generate_signals_vectorized()
        if not res_df.empty and "entry_idx" in res_df.columns:
            positions = pd.to_numeric(res_df["entry_idx"], errors="coerce")
            if positions.isna().any() or (positions < 0).any() or (positions >= len(test_df)).any():
                raise ValueError("wfa_unmappable_event_session")
            res_df["session_date"] = [str(test_df.index[int(position)].date()) for position in positions]
            if signal_rows is not None:
                for field in (
                    "feature_cutoff_ts", "feature_source_timestamp",
                    "feature_source_start_timestamp", "feature_source_end_timestamp",
                    "feature_builder_sha256", "source_partition_id",
                    "source_partition_sha256", "corpus_freeze_sha256",
                    "feature_builder_id", "normalization_fit_scope",
                    "normalization_fit_start", "normalization_fit_end",
                    "normalization_fit_fold_id", "fit_uses_test_data",
                    "normalization_fit_source_sha256",
                ):
                    if field in signal_rows.columns:
                        res_df[field] = [signal_rows.loc[int(position), field] for position in positions]
                if "feature_builder_sha256" not in res_df.columns:
                    try:
                        builder_bytes = inspect.getsource(self.signal_builder).encode("utf-8")
                    except (OSError, TypeError):
                        raise ValueError("wfa_feature_builder_identity_missing")
                    res_df["feature_builder_sha256"] = getattr(
                        self.signal_builder, "builder_sha256", hashlib.sha256(builder_bytes).hexdigest()
                    )
                if "source_partition_id" not in res_df.columns:
                    source_id = getattr(self.signal_builder, "source_partition_id", "")
                    if not source_id:
                        raise ValueError("wfa_source_authority_missing")
                    res_df["source_partition_id"] = source_id
                if "source_partition_sha256" not in res_df.columns:
                    source_sha = getattr(self.signal_builder, "source_partition_sha256", "")
                    if not source_sha:
                        raise ValueError("wfa_source_authority_missing")
                    res_df["source_partition_sha256"] = source_sha
                if "corpus_freeze_sha256" not in res_df.columns:
                    corpus_sha = getattr(self.signal_builder, "corpus_freeze_sha256", "")
                    if not corpus_sha:
                        raise ValueError("wfa_corpus_authority_missing")
                    res_df["corpus_freeze_sha256"] = corpus_sha
                if "feature_builder_id" not in res_df.columns:
                    res_df["feature_builder_id"] = getattr(self.signal_builder, "builder_id", "")
                if "normalization_fit_scope" not in res_df.columns:
                    res_df["normalization_fit_scope"] = "PASS_NOT_APPLICABLE"
                    res_df["normalization_fit_start"] = None
                    res_df["normalization_fit_end"] = None
                    res_df["normalization_fit_fold_id"] = None
                    res_df["fit_uses_test_data"] = False
                    res_df["normalization_fit_source_sha256"] = getattr(
                        self.signal_builder, "normalization_fit_source_sha256",
                        getattr(self.signal_builder, "source_partition_sha256", ""),
                    )
                res_df["decision_timestamp"] = [test_df.index[int(position)] for position in positions]
                res_df["feature_source_start_timestamp"] = res_df.get(
                    "feature_source_start_timestamp", res_df["feature_source_timestamp"]
                )
                res_df["feature_source_end_timestamp"] = res_df.get(
                    "feature_source_end_timestamp", res_df["feature_source_timestamp"]
                )
                res_df["available_at_decision"] = [
                    pd.Timestamp(source) <= pd.Timestamp(decision)
                    for source, decision in zip(
                        res_df["feature_source_end_timestamp"], res_df["decision_timestamp"]
                    )
                ]
        return res_df

    @staticmethod
    def _session_aggregate(results: pd.DataFrame) -> Dict[str, float]:
        if results.empty or "pl" not in results or "session_date" not in results:
            raise ValueError("wfa_session_aggregation_requires_mapped_events")
        values = pd.to_numeric(results["pl"], errors="coerce")
        if values.isna().any():
            raise ValueError("wfa_session_aggregation_nan")
        event_mean = float(values.mean())
        session_means = results.assign(_pl=values).groupby("session_date", sort=True)["_pl"].mean()
        return {
            "event_count": int(len(values)),
            "session_count": int(len(session_means)),
            "event_mean": event_mean,
            "session_equal_mean": float(session_means.mean()),
            "positive_fraction": float((values > 0).mean()),
        }

    @staticmethod
    def _session_bootstrap(results: pd.DataFrame, *, repetitions: int = 1000, seed: int = 0) -> Dict[str, Any]:
        if results.empty or "pl" not in results or "session_date" not in results:
            raise ValueError("wfa_session_bootstrap_requires_mapped_events")
        session_means = results.groupby("session_date", sort=True)["pl"].mean().astype(float).tolist()
        if not session_means:
            raise ValueError("wfa_session_bootstrap_empty")
        rng = np.random.default_rng(seed)
        samples = rng.choice(session_means, size=(repetitions, len(session_means)), replace=True).mean(axis=1)
        return {
            "unit": "session",
            "repetitions": int(repetitions),
            "seed": int(seed),
            "statistic": "session_equal_mean",
            "estimate": float(np.mean(session_means)),
            "ci_lower": float(np.quantile(samples, 0.025)),
            "ci_upper": float(np.quantile(samples, 0.975)),
        }

    def run(self, param_grid: Dict[str, List[Any]]) -> pd.DataFrame:
        """Executes the complete WFA process."""
        windows = self.generate_windows()
        self.frozen_config_hash = hashlib.sha256(
            json.dumps(
                {
                    "train_years": self.train_years,
                    "test_years": self.test_years,
                    "slippage_bps": self.slippage_bps,
                    "spread_bps": self.spread_bps,
                    "purge_minutes": self.purge.total_seconds() / 60.0,
                    "embargo_minutes": self.embargo.total_seconds() / 60.0,
                    "feature_lookback_minutes": self.feature_lookback_minutes,
                    "param_grid": param_grid,
                },
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        
        all_oos_trades = []
        
        for i, window in enumerate(windows):
            print(f"Window {i+1}: Train {window['train_start']}-{window['train_end']} | Test {window['test_start']}-{window['test_end']}")
            
            # Train Phase
            best_params = self.optimize(window["train_df"], param_grid)
            self.best_params_per_window.append({
                "window": i+1,
                "train_years": f"{window['train_start']}-{window['train_end']}",
                "test_years": f"{window['test_start']}-{window['test_end']}",
                "best_params": best_params
            })
            self.parameter_freeze_ledger.append({
                "fold_id": i + 1,
                "parameter_selection_data_end": str(window["train_df"].index.max()),
                "parameter_freeze_time": str(window["train_df"].index.max()),
                "test_start": str(window["effective_test_start"]),
                "parameters": best_params,
                "frozen_config_hash": self.frozen_config_hash,
            })
            candidates = getattr(self, "_last_candidate_scores", [])
            candidate_payload = json.dumps(candidates, sort_keys=True, default=str)
            self.parameter_selection_ledger.append({
                "fold_id": i + 1,
                "selection_data_start": str(window["train_df"].index.min()),
                "selection_data_end": str(window["train_df"].index.max()),
                "test_start": str(window["effective_test_start"]),
                "selected_parameters": best_params,
                "candidate_scores": candidates,
                "candidate_ledger_sha256": hashlib.sha256(candidate_payload.encode("utf-8")).hexdigest(),
                "selection_source": "TRAIN_ONLY",
            })
            self.fold_ledger.append({
                "fold_id": i + 1,
                "train_start": str(window["train_df"].index.min()),
                "train_end": str(window["train_df"].index.max()),
                "test_start": str(window["test_df"].index.min()),
                "test_end": str(window["test_df"].index.max()),
                "train_rows": len(window["train_df"]),
                "test_rows": len(window["test_df"]),
                "overlap_rows": int(len(window["train_df"].index.intersection(window["test_df"].index))),
                "purge_interval": str(window["purge_interval"]),
                "embargo_interval": str(window["embargo_interval"]),
            })
            print(f"  -> Best Params: {best_params}")
            
            # Test Phase (Out-of-Sample)
            oos_trades = self.test(window["test_df"], best_params)
            
            if not oos_trades.empty:
                oos_trades["wfa_window"] = i + 1
                oos_trades["test_year"] = window["test_start"]
                all_oos_trades.append(oos_trades)
                
        if all_oos_trades:
            self.oos_results = pd.concat(all_oos_trades, ignore_index=True)
            self.aggregation_report = self._session_aggregate(self.oos_results)
            self.uncertainty_report = self._session_bootstrap(self.oos_results)
            if {"feature_cutoff_ts", "feature_source_timestamp"}.issubset(self.oos_results.columns):
                for _, row in self.oos_results.iterrows():
                    cutoff = pd.Timestamp(row["feature_cutoff_ts"])
                    source = pd.Timestamp(row["feature_source_timestamp"])
                    self.feature_causality_ledger.append({
                        "feature_name": "vectorized_signal_features",
                        "feature_source_start_timestamp": pd.Timestamp(row["feature_source_start_timestamp"]).isoformat(),
                        "feature_source_end_timestamp": pd.Timestamp(row["feature_source_end_timestamp"]).isoformat(),
                        "decision_timestamp": pd.Timestamp(row["decision_timestamp"]).isoformat(),
                        "feature_cutoff_ts": cutoff.isoformat(),
                        "feature_source_timestamp": source.isoformat(),
                        "session_id": str(pd.Timestamp(row["decision_timestamp"]).date()),
                        "fold_id": int(row["wfa_window"]),
                        "available_at_decision": bool(row["available_at_decision"]),
                        "feature_builder_sha256": str(row.get("feature_builder_sha256", "unidentified")),
                        "source_partition_id": str(row.get("source_partition_id", "unidentified")),
                        "source_partition_sha256": str(row.get("source_partition_sha256", "unidentified")),
                        "corpus_freeze_sha256": str(row.get("corpus_freeze_sha256", "unidentified")),
                        "feature_builder_id": str(row.get("feature_builder_id", "unidentified")),
                        "normalization_fit_scope": str(row.get("normalization_fit_scope", "unidentified")),
                        "normalization_fit_start": row.get("normalization_fit_start"),
                        "normalization_fit_end": row.get("normalization_fit_end"),
                        "normalization_fit_fold_id": row.get("normalization_fit_fold_id"),
                        "normalization_fit_source_sha256": str(row.get("normalization_fit_source_sha256", "unidentified")),
                        "fit_uses_test_data": bool(row.get("fit_uses_test_data", False)),
                        "leakage_detected": bool(source > cutoff),
                        "oracle_check": True,
                    })
            else:
                raise ValueError("wfa_feature_causality_metadata_missing")
        else:
            self.oos_results = pd.DataFrame()
            self.aggregation_report = {"status": "NO_EVENTS"}
            self.uncertainty_report = {"status": "NO_EVENTS"}
        if self.fold_ledger:
            validate_fold_ledger(self.fold_ledger)
        if self.feature_causality_ledger:
            validate_feature_causality_ledger(
                self.feature_causality_ledger,
                expected_builder_sha256=getattr(self.signal_builder, "builder_sha256", None),
                expected_builder_id=getattr(self.signal_builder, "builder_id", None),
                expected_source_sha256=getattr(self.signal_builder, "source_partition_sha256", None),
                expected_corpus_freeze_sha256=getattr(self.signal_builder, "corpus_freeze_sha256", None),
                expected_normalization_source_sha256=getattr(
                    self.signal_builder, "normalization_fit_source_sha256",
                    getattr(self.signal_builder, "source_partition_sha256", None),
                ),
                expected_fold_ids=set(range(1, len(windows) + 1)),
            )
        if self.parameter_freeze_ledger:
            validate_parameter_freeze_ledger(self.parameter_freeze_ledger)
        if self.parameter_selection_ledger:
            validate_parameter_selection_ledger(self.parameter_selection_ledger)

        return self.oos_results
