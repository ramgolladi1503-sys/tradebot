# WORK ITEM: FEAT-SENTINEL-WALL-OBSERVER-001
**Title:** Sentinel Wall Intelligence — Stage 1: In-Memory Strike Wall Observer & Heatmap Visualization  
**Status:** ARCHITECTURE & INITIAL IMPLEMENTATION  
**Safety Classification:** NON-INVASIVE READ-ONLY SUPERVISORY ADVISORY & RESEARCH  
**Safety Invariants:** `read_only=True`, `is_order_action=False`, `broker_api_called=False`, `allowed_for_live_execution=False`, `edge_certification_status="NO_CERTIFIED_EDGE"`

---

## 1. Problem Statement & Scope
TradeBot has an active live stream subscribing to 126 liquid option strikes and indices with full Level-5 order book depth, Open Interest (OI), and volume. However, this strike-level positioning data is currently analyzed independently per contract rather than aggregated into an institutional **Strike-Level Structural Wall Heatmap** (Call Walls, Put Walls, Net Gamma Exposure proxies, and Order Book Absorption zones).

### Scope (Stage 1: Wall Observer)
1. **Strike Positioning Aggregator (`core/market_structure/sentinel_wall_observer.py`)**:
   - Ingests in-memory ticks across all subscribed strikes.
   - Extracts strike, expiry, call/put type from symbol strings.
   - Computes total Call OI, Put OI, $\Delta \text{OI}$, Executed Volume, and resting Bid/Ask depth per strike.
   - Identifies key structural levels:
     - **Major Call Wall Strike**: $\arg\max_{\text{strike}} \text{OI}_{CE}$
     - **Major Put Wall Strike**: $\arg\max_{\text{strike}} \text{OI}_{PE}$
     - **Secondary Walls & Local Absorption Nodes**: Strikes with $> 75\%$ of max OI.
     - **Spot Proximity**: Distance (in index points and ATR multiples) from current spot to nearest major wall.
2. **Dashboard Visual Heatmap Component**:
   - Add a dedicated interactive strike-ladder heatmap visualization to `scripts/run_sentinel_dashboard.py`.
   - Real-time strike ladder showing Call Wall concentrations (Red), Put Wall concentrations (Green), and active Spot trajectory (Bright Cyan line).
3. **Post-Development Multi-Disciplinary Adversarial Attack Audit**:
   - Following implementation, the 5 domain attackers (Microstructure, Statistical, Systems, Options Greeks, Risk Governance) will challenge the model, stress-test its edge assumptions, and calibrate wall breach vs rejection parameters for Stage 2.

---

## 2. Hermes Architectural Specification & Invariant Contracts

### Source Agent & Role Contract
```yaml
source_agent: hermes
action: DESIGN_ARCHITECTURE
title: Sentinel Wall Observer & Heatmap Data Contract Architecture
scope: In-memory options strike profiling, wall detection, advisory proximity checks, and read-only supervisory state export.
requested_paths:
  - core/market_structure/sentinel_wall_observer.py
  - docs/tradebot_delivery/work_items/FEAT-SENTINEL-WALL-OBSERVER-001.md
allowed_paths:
  - core/market_structure/sentinel_wall_observer.py
  - docs/tradebot_delivery/work_items/FEAT-SENTINEL-WALL-OBSERVER-001.md
forbidden_paths:
  - core/order*
  - core/execution*
  - core/broker*
  - core/risk*
  - config/
  - credentials.py
  - .env
expected_tests:
  - tests/test_sentinel_wall_observer.py
acceptance_proof:
  - Zero allocation or mutation during tick updates.
  - Strict immutable read-only safety invariants verified on every generated state snapshot.
  - Deterministic identification of major Call/Put walls, Net OI imbalance, and distance in index points.
  - Safe parsing of symbol strings (NIFTY/BANKNIFTY weekly and monthly option ticker formats) without crash on malformed data.
```

### Safety & Compliance Invariants
```python
read_only: bool = True
is_order_action: bool = False
broker_api_called: bool = False
allowed_for_live_execution: bool = False
edge_certification_status: str = "NO_CERTIFIED_EDGE"
```
The observer is an offline/in-memory supervisory intelligence module. It must **never** invoke broker endpoints, trigger order actions, or alter live trading configurations. All state exports must declare `read_only=True`, `is_order_action=False`, and `broker_api_called=False`.

---

### Data Schema Design

#### 1. `StrikeWallProfile` Dataclass
Represents aggregated positioning and depth attributes for a discrete option strike:
```python
@dataclass(frozen=True)
class StrikeWallProfile:
    strike: float
    call_oi: float = 0.0
    put_oi: float = 0.0
    call_volume: float = 0.0
    put_volume: float = 0.0
    call_bid_depth: float = 0.0
    call_ask_depth: float = 0.0
    put_bid_depth: float = 0.0
    put_ask_depth: float = 0.0
    net_oi_imbalance: float = 0.0       # Put OI - Call OI (Positive indicates Put dominance / Bullish floor)
    is_major_call_wall: bool = False    # True if strike equals max Call OI across all observed strikes
    is_major_put_wall: bool = False     # True if strike equals max Put OI across all observed strikes
    is_secondary_call_wall: bool = False # Call OI >= 0.75 * max Call OI
    is_secondary_put_wall: bool = False  # Put OI >= 0.75 * max Put OI
```

#### 2. `SentinelWallState` Dataclass
Represents the point-in-time structural wall snapshot:
```python
@dataclass(frozen=True)
class SentinelWallState:
    timestamp_ms: int
    symbol: str
    spot_price: float
    major_call_wall_strike: float
    major_put_wall_strike: float
    distance_to_call_wall_pts: float    # major_call_wall_strike - spot_price
    distance_to_put_wall_pts: float     # spot_price - major_put_wall_strike
    total_call_oi: float
    total_put_oi: float
    pcr_oi: float                       # total_put_oi / total_call_oi (safe division with 0 fallback)
    wall_density_map: Dict[float, StrikeWallProfile]  # Sorted strike -> StrikeWallProfile mapping
    # Safety Invariants
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False
    edge_certification_status: str = "NO_CERTIFIED_EDGE"
```

---

### Class Architecture: `SentinelWallObserver`

```python
class SentinelWallObserver:
    """
    High-performance in-memory strike wall observer.
    Ingests streaming ticks and order book depth for option chain contracts,
    maintains strike-level aggregations, and computes structural wall states.
    """
    def __init__(self, underlying_symbol: str = "NIFTY") -> None:
        self.underlying_symbol = underlying_symbol
        self._spot_price: float = 0.0
        self._last_timestamp_ms: int = 0
        # Internal mutable state indexed by (strike, option_type)
        # Separate mapping for fast lookups and aggregations:
        # strike -> {'CE': {...}, 'PE': {...}}
        self._strike_data: Dict[float, Dict[str, Dict[str, float]]] = {}
    
    def on_spot_tick(self, timestamp_ms: int, spot_price: float) -> None:
        """Update spot price reference."""
        ...

    def on_option_tick(self, timestamp_ms: int, symbol: str, oi: float, volume: float,
                       bid_depth: float = 0.0, ask_depth: float = 0.0) -> None:
        """
        Ingest option tick with L5 resting depth.
        Extracts strike and option type (CE/PE) via regex/string parsing.
        Updates strike aggregation buckets.
        """
        ...

    def compute_wall_state(self) -> SentinelWallState:
        """
        Constructs an immutable SentinelWallState snapshot on-demand:
        - Evaluates max Call OI and Put OI strikes.
        - Identifies primary and secondary walls (>75% max OI).
        - Computes distance from spot in points.
        - Returns frozen SentinelWallState with safety invariants.
        """
        ...

    def is_spot_near_call_wall(self, threshold_pts: float = 50.0) -> bool:
        """Advisory check: spot within threshold_pts of major call wall."""
        ...

    def is_spot_near_put_wall(self, threshold_pts: float = 50.0) -> bool:
        """Advisory check: spot within threshold_pts of major put wall."""
        ...

    def get_absorption_zones(self, min_depth_ratio: float = 2.0) -> List[float]:
        """Identifies strikes where order book depth exhibits significant resting absorption imbalance."""
        ...
```

### Microstructure & Symbol Parsing Specification
The option symbol parser must handle standard Indian NSE weekly/monthly option formats:
- E.g., `NIFTY26OCT25000CE`, `BANKNIFTY24DEC50000PE`, `NIFTY24O2425000CE`
- Robust regex: `r"^([A-Z]+)\d{2}[A-Z0-9]{3,5}(\d+(?:\.\d+)?)(CE|PE)$"` with fallback parser for alternative delimiter formats (e.g. `NIFTY-25000-CE`).
- Malformed or unrecognized symbols must fail silently or log debug messages without raising exceptions or breaking the tick ingestion loop.

---

### GSD Execution Directive (Stage 2)
The execution agent (GSD) is hereby authorized to:
1. Implement `core/market_structure/sentinel_wall_observer.py` conforming to the exact dataclass contracts, invariants, and performance requirements above.
2. Develop unit test suite `tests/test_sentinel_wall_observer.py` testing:
   - Symbol parsing robustness (valid, irregular, malformed).
   - Accurate Open Interest, Volume, and Resting Depth accumulation.
   - Primary and secondary wall detection logic.
   - Correct distance metrics and edge cases (zero OI, missing strikes, spot above/below all walls).
   - Immutability and invariant assertions (`read_only=True`, `is_order_action=False`, `broker_api_called=False`).
   - Latency / execution benchmark showing sub-millisecond execution for standard 126-strike option chains.
