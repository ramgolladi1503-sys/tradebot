from pathlib import Path
from .statistics_models import StatisticalValidationReport

class ReportGenerator:
    def __init__(self, output_dir: str = "docs/statistical_validation"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def generate(self, report: StatisticalValidationReport) -> None:
        self._write_01_data_inventory(report)
        self._write_02_sample_validation(report)
        self._write_03_expectancy(report)
        self._write_04_profit_factor(report)
        self._write_05_drawdown(report)
        self._write_06_distribution(report)
        self._write_07_bootstrap(report)
        self._write_08_cost_sensitivity(report)
        self._write_09_regime_analysis(report)
        self._write_10_walk_forward(report)
        self._write_11_stability(report)
        self._write_12_validation_summary(report)
        
    def _write_01_data_inventory(self, r: StatisticalValidationReport):
        path = self.output_dir / "01_data_inventory.md"
        with open(path, "w") as f:
            f.write(f"# Data Inventory\n\nRun ID: {r.run_id}\n\n")
            f.write(f"- Usable Records: {r.sample_validation.usable_sample_size}\n")
            f.write(f"- Rejected Records: {r.sample_validation.rejected_sample_size}\n")
            f.write(f"- Unusable/Insufficient Records: {r.sample_validation.insufficient_evidence_count}\n")
            f.write(f"- Ambiguous Outcomes: {r.sample_validation.ambiguous_count}\n")
            f.write(f"- Missing Trace Data: {r.sample_validation.missing_trace_count}\n")
            f.write(f"- Hypothetical Records: {r.sample_validation.hypothetical_count}\n")
            
    def _write_02_sample_validation(self, r: StatisticalValidationReport):
        path = self.output_dir / "02_sample_validation.md"
        with open(path, "w") as f:
            f.write(f"# Sample Validation\n\nStatus: {r.sample_validation.status.value}\n\n")
            f.write(f"Total Records: {r.sample_validation.total_records}\n")
            f.write(f"Executable Count: {r.sample_validation.executable_count}\n")
            if r.sample_validation.status.value == "INSUFFICIENT_SAMPLE":
                f.write("\n> WARNING: INSUFFICIENT_SAMPLE. Metrics will not be extrapolated.\n")
                
    def _write_03_expectancy(self, r: StatisticalValidationReport):
        path = self.output_dir / "03_expectancy.md"
        with open(path, "w") as f:
            f.write(f"# Expectancy\n\nStatus: {r.expectancy.status.value}\n\n")
            if r.expectancy.average_net_pnl is not None:
                f.write(f"- Average Net PnL: {r.expectancy.average_net_pnl:.2f}\n")
                f.write(f"- Average Gross PnL: {r.expectancy.average_gross_pnl:.2f}\n")
                f.write(f"- Average Points: {r.expectancy.average_points:.2f}\n")
                f.write(f"- Average R: {r.expectancy.average_r:.2f}\n")
            f.write(f"\nBreakdown:\n- Wins: {r.expectancy.win_count}\n- Losses: {r.expectancy.loss_count}\n- Timeouts: {r.expectancy.timeout_count}\n")

    def _write_04_profit_factor(self, r: StatisticalValidationReport):
        path = self.output_dir / "04_profit_factor.md"
        with open(path, "w") as f:
            f.write(f"# Profit Factor\n\nStatus: {r.profit_factor.status.value}\n\n")
            if r.profit_factor.gross_profits is not None:
                f.write(f"- Gross Profits (Net): {r.profit_factor.gross_profits:.2f}\n")
                f.write(f"- Gross Losses (Net): {r.profit_factor.gross_losses:.2f}\n")
            if r.profit_factor.profit_factor is not None:
                f.write(f"- Profit Factor: {r.profit_factor.profit_factor:.2f}\n")

    def _write_05_drawdown(self, r: StatisticalValidationReport):
        path = self.output_dir / "05_drawdown.md"
        with open(path, "w") as f:
            f.write(f"# Drawdown\n\nStatus: {r.drawdown.status.value}\n\n")
            if r.drawdown.maximum_drawdown is not None:
                f.write(f"- Maximum Drawdown: {r.drawdown.maximum_drawdown:.2f}\n")
                f.write(f"- Max Drawdown Duration (s): {r.drawdown.max_drawdown_duration_seconds:.2f}\n")
                f.write(f"- Peak Equity: {r.drawdown.peak_equity:.2f}\n")

    def _write_06_distribution(self, r: StatisticalValidationReport):
        path = self.output_dir / "06_distribution.md"
        with open(path, "w") as f:
            f.write(f"# Distribution\n\nStatus: {r.distribution.status.value}\n\n")
            def _write_stats(name, stats):
                if stats:
                    f.write(f"## {name}\n")
                    f.write(f"- Mean: {stats.mean:.2f}\n- Median: {stats.median:.2f}\n")
                    f.write(f"- StdDev: {stats.standard_deviation:.2f}\n- Variance: {stats.variance:.2f}\n")
                    f.write(f"- 5th Percentile: {stats.percentile_5:.2f}\n")
                    f.write(f"- 95th Percentile: {stats.percentile_95:.2f}\n\n")
            _write_stats("Win Distribution", r.distribution.win_distribution)
            _write_stats("Loss Distribution", r.distribution.loss_distribution)
            _write_stats("R Distribution", r.distribution.r_distribution)
            _write_stats("Duration Distribution", r.distribution.duration_distribution)

    def _write_07_bootstrap(self, r: StatisticalValidationReport):
        path = self.output_dir / "07_bootstrap.md"
        with open(path, "w") as f:
            f.write(f"# Bootstrap Confidence\n\nConfidence Level: {r.bootstrap.status.value}\n\n")
            def _w_ci(name, ci):
                if ci:
                    f.write(f"## {name}\n")
                    f.write(f"Mean Estimate: {ci.mean_estimate:.2f}\n")
                    f.write(f"95% CI: [{ci.lower_bound:.2f}, {ci.upper_bound:.2f}]\n\n")
            _w_ci("Expectancy CI", r.bootstrap.expectancy_ci)
            _w_ci("Profit Factor CI", r.bootstrap.profit_factor_ci)
            _w_ci("Mean R CI", r.bootstrap.mean_r_ci)

    def _write_08_cost_sensitivity(self, r: StatisticalValidationReport):
        path = self.output_dir / "08_cost_sensitivity.md"
        with open(path, "w") as f:
            f.write(f"# Cost Sensitivity\n\nStatus: {r.cost_sensitivity.status.value}\n\n")
            if r.cost_sensitivity.estimated_slippage_expectancy is not None:
                f.write(f"- No Slippage Expectancy: {r.cost_sensitivity.no_slippage_expectancy:.2f}\n")
                f.write(f"- Estimated Slippage Expectancy: {r.cost_sensitivity.estimated_slippage_expectancy:.2f}\n")
                f.write(f"- Increased Slippage Expectancy: {r.cost_sensitivity.increased_slippage_expectancy:.2f}\n")
                f.write(f"- Higher Brokerage Expectancy: {r.cost_sensitivity.higher_brokerage_expectancy:.2f}\n")
                f.write(f"- Spread Expansion Expectancy: {r.cost_sensitivity.spread_expansion_expectancy:.2f}\n")
                f.write(f"- Remains Positive Under Stress: {r.cost_sensitivity.remains_positive_under_stress}\n")

    def _write_09_regime_analysis(self, r: StatisticalValidationReport):
        path = self.output_dir / "09_regime_analysis.md"
        with open(path, "w") as f:
            f.write(f"# Regime Analysis\n\nStatus: {r.regime_analysis.status.value}\n\n")
            def _w_regimes(name, metric_dict):
                f.write(f"## {name}\n")
                for k, v in metric_dict.items():
                    f.write(f"- {k}: Sample={v.sample_size}, Expectancy={v.expectancy}, PF={v.profit_factor}, Conf={v.confidence.value}\n")
                f.write("\n")
            _w_regimes("Trend", r.regime_analysis.trend_metrics)
            _w_regimes("Range", r.regime_analysis.range_metrics)
            _w_regimes("Volatility", r.regime_analysis.volatility_metrics)

    def _write_10_walk_forward(self, r: StatisticalValidationReport):
        path = self.output_dir / "10_walk_forward.md"
        with open(path, "w") as f:
            f.write(f"# Walk Forward Stability\n\nStatus: {r.walk_forward.status.value}\n\n")
            for i, w in enumerate(r.walk_forward.windows):
                f.write(f"## Window {i+1}\n")
                f.write(f"- Sample Size: {w.sample_size}\n")
                f.write(f"- Expectancy: {w.expectancy}\n")
                f.write(f"- Profit Factor: {w.profit_factor}\n\n")

    def _write_11_stability(self, r: StatisticalValidationReport):
        path = self.output_dir / "11_stability.md"
        with open(path, "w") as f:
            f.write(f"# Stability Metrics\n\nStatus: {r.stability.status.value}\n\n")
            f.write(f"- Performance Drift: {r.stability.performance_drift}\n")
            f.write(f"- Performance Collapse Detected: {r.stability.performance_collapse_detected}\n")
            f.write(f"- Performance Improvement Detected: {r.stability.performance_improvement_detected}\n")

    def _write_12_validation_summary(self, r: StatisticalValidationReport):
        path = self.output_dir / "12_validation_summary.md"
        with open(path, "w") as f:
            f.write("# Validation Summary\n\n")
            f.write("## Assumptions\n")
            for a in r.assumptions:
                f.write(f"- {a}\n")
            f.write("\n## Limitations\n")
            for a in r.limitations:
                f.write(f"- {a}\n")
            f.write("\n## Warnings\n")
            for a in r.warnings:
                f.write(f"- {a}\n")
