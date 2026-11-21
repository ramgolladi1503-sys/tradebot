# OptionMate SENSEX Strategy: Dynamic Black-Scholes Anchor Replay (Jan – Jul 2026)

## 1. Executive Correction: Dynamic Premium vs Static Placeholder

In earlier scratch scripts, a static placeholder of `₹140.0` was mistakenly assigned to all non-expiry rows. 

The replay engine (`scripts/research/run_sensex_optionmate_realistic_backtest.py`) has been fully updated to compute the **live dynamic Black-Scholes ATM half-straddle sustainable price anchor**:

$$\text{Sustainable Anchor} = 0.40 \times \text{Spot} \times \left(\frac{\max(\text{VIX}, 9.0)}{100}\right) \times \sqrt{\frac{\max(\text{DTE}, 0.20)}{365}}$$

### How OptionMate Dynamically Sets Premium by Day of Week:
1. **Expiry Thursdays (0-DTE, $\text{DTE} = 0.20$)**:
   - Dynamic ATM Half-Straddle Anchor: **₹90 – ₹105**
   - OptionMate strictly prohibits buying ATM options due to 0-DTE gamma/theta crush.
   - Selected Contract: $RP_2$ OTM Slingshot strike entering on the **₹28 – ₹48 ladder** (average entry ₹38).
2. **1-DTE (Wednesdays, $\text{DTE} = 1.0$)**:
   - Dynamic ATM Anchor: **₹210 – ₹240**
   - $RP_2$ OTM Entry Premium (~55% of anchor): **₹115 – ₹132**
3. **2-DTE (Tuesdays, $\text{DTE} = 2.0$)**:
   - Dynamic ATM Anchor: **₹295 – ₹335**
   - $RP_2$ OTM Entry Premium (~55% of anchor): **₹161 – ₹185**
4. **3-DTE (Mondays, $\text{DTE} = 3.0$)**:
   - Dynamic ATM Anchor: **₹360 – ₹410**
   - $RP_2$ OTM Entry Premium (~55% of anchor): **₹197 – ₹225**
5. **4-DTE (Fridays, $\text{DTE} = 4.0$)**:
   - Dynamic ATM Anchor: **₹420 – ₹465**
   - $RP_2$ OTM Entry Premium (~55% of anchor): **₹231 – ₹255**

---

## 2. Updated Overall Performance (125 Sessions)

| Metric | Expiry Thursdays (0-DTE) | Non-Expiry Days (1 to 4 DTE) | Combined Total |
| :--- | :--- | :--- | :--- |
| **Total Sessions** | **24** | **101** | **125** |
| **Gate 2 Filtered / Stand-Aside** | 21 (87.5%) | 80 (79.2%) | 101 (80.8%) |
| **Trades Fired** | **3** | **21** | **24** |
| **Winning Trades** | 1 (33.3%) | 12 (57.1%) | 13 (54.2%) |
| **Losing Trades** | 2 (66.7%) | 9 (42.9%) | 11 (45.8%) |
| **Net PnL per Lot (20 Qty)** | **-₹152.00** | **+₹9,216.50** | **+₹9,064.50** |
| **Average PnL per Trade** | -₹50.67 | +₹438.88 | +₹377.69 |
| **Profit Factor** | 0.72 | **2.62** | **2.38** |

---

## 3. Dynamic Non-Expiry Trades: Day-by-Day Trade Log

Every trade dynamically calculates its ATM anchor and OTM entry premium from spot and DTE:

| Date | Day | DTE | Dir | Time | Emitted Contract | ATM Anchor | Entry Prem | Exit Prem | Pts | PnL (20 Qty) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **2026-01-07** | Wed | 1.0 | CALL | 09:20 | `SENSEX 85500 CE` | ₹240.0 | ₹132.0 | ₹112.2 | -19.8 | -₹396.00 | EOD_SQUAREOFF |
| **2026-01-28** | Wed | 1.0 | CALL | 09:20 | `SENSEX 83100 CE` | ₹232.9 | ₹128.1 | ₹102.5 | -25.6 | -₹512.40 | STOP_LOSS_HIT |
| **2026-02-02** | Mon | 3.0 | CALL | 09:20 | `SENSEX 81300 CE` | ₹395.5 | ₹217.5 | ₹261.0 | +43.5 | **+₹870.00** | TRAILED_COST_EXIT ($RP_1$) |
| **2026-02-03** | Tue | 2.0 | PUT | 09:30 | `SENSEX 83400 PE` | ₹335.9 | ₹184.7 | ₹221.6 | +36.9 | **+₹738.80** | TRAILED_COST_EXIT ($RP_1$) |
| **2026-02-04** | Wed | 1.0 | CALL | 09:20 | `SENSEX 84300 CE` | ₹236.3 | ₹130.0 | ₹110.5 | -19.5 | -₹390.00 | EOD_SQUAREOFF |
| **2026-02-23** | Mon | 3.0 | CALL | 09:20 | `SENSEX 83700 CE` | ₹407.6 | ₹224.2 | ₹269.0 | +44.8 | **+₹896.80** | TRAILED_COST_EXIT ($RP_1$) |
| **2026-02-24** | Tue | 2.0 | PUT | 09:20 | `SENSEX 82200 PE` | ₹330.9 | ₹182.0 | ₹286.7 | +104.7 | **+₹2,093.00** | **TARGET_RP2_HIT** |
| **2026-02-25** | Wed | 1.0 | CALL | 09:55 | `SENSEX 83400 CE` | ₹233.7 | ₹128.5 | ₹102.8 | -25.7 | -₹514.00 | STOP_LOSS_HIT |
| **2026-02-27** | Fri | 4.0 | PUT | 09:25 | `SENSEX 81300 PE` | ₹463.1 | ₹254.7 | ₹401.2 | +146.5 | **+₹2,929.05** | **TARGET_RP2_HIT** |
| **2026-03-02** | Mon | 3.0 | CALL | 09:20 | `SENSEX 81000 CE` | ₹392.9 | ₹216.1 | ₹183.7 | -32.4 | -₹648.30 | EOD_SQUAREOFF |
| **2026-03-10** | Tue | 2.0 | PUT | 09:20 | `SENSEX 77400 PE` | ₹311.7 | ₹171.4 | ₹145.7 | -25.7 | -₹514.20 | EOD_SQUAREOFF |
| **2026-03-20** | Fri | 4.0 | CALL | 09:20 | `SENSEX 75600 CE` | ₹424.7 | ₹233.6 | ₹186.9 | -46.7 | -₹934.40 | STOP_LOSS_HIT |
| **2026-03-23** | Mon | 3.0 | PUT | 09:55 | `SENSEX 72600 PE` | ₹358.1 | ₹197.0 | ₹236.4 | +39.4 | **+₹788.00** | TRAILED_COST_EXIT ($RP_1$) |
| **2026-03-24** | Tue | 2.0 | PUT | 09:20 | `SENSEX 72900 PE` | ₹293.9 | ₹161.6 | ₹193.9 | +32.3 | **+₹646.40** | TRAILED_COST_EXIT ($RP_1$) |
| **2026-03-27** | Fri | 4.0 | PUT | 09:20 | `SENSEX 73800 PE` | ₹420.6 | ₹231.3 | ₹364.3 | +133.0 | **+₹2,659.95** | **TARGET_RP2_HIT** |
| **2026-04-21** | Tue | 2.0 | CALL | 09:20 | `SENSEX 79500 CE` | ₹315.4 | ₹173.5 | ₹208.2 | +34.7 | **+₹694.00** | HALF_RP1_EOD |
| **2026-05-11** | Mon | 3.0 | PUT | 09:20 | `SENSEX 75900 PE` | ₹374.1 | ₹205.8 | ₹247.0 | +41.2 | **+₹823.20** | TRAILED_COST_EXIT ($RP_1$) |
| **2026-05-18** | Mon | 3.0 | PUT | 09:35 | `SENSEX 73800 PE` | ₹364.5 | ₹200.5 | ₹160.4 | -40.1 | -₹802.00 | STOP_LOSS_HIT |
| **2026-06-03** | Wed | 1.0 | PUT | 09:20 | `SENSEX 73500 PE` | ₹209.0 | ₹115.0 | ₹138.0 | +23.0 | **+₹460.00** | TRAILED_COST_EXIT ($RP_1$) |
| **2026-06-10** | Wed | 1.0 | CALL | 09:45 | `SENSEX 75000 CE` | ₹209.9 | ₹115.4 | ₹98.1 | -17.3 | -₹346.20 | EOD_SQUAREOFF |
| **2026-06-30** | Tue | 2.0 | PUT | 09:20 | `SENSEX 76200 PE` | ₹306.8 | ₹168.7 | ₹202.4 | +33.7 | **+₹674.80** | TRAILED_COST_EXIT ($RP_1$) |

---

## 4. Expiry Thursdays (0-DTE) Trade Log

Gate 2 filters stood aside on **21 out of 24 Expiry Thursdays (87.5%)**. 

| Date | Day | DTE | Dir | Time | Emitted Contract | ATM Anchor | Entry Prem | Exit Prem | Pts | PnL (20 Qty) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **2026-01-29** | Thu | 0.2 | PUT | 09:20 | `SENSEX 81600 PE` | ₹103.8 | ₹38.0 | ₹57.0 | +19.0 | **+₹380.00** | TRAILED_COST_EXIT ($RP_1$ hit) |
| **2026-04-02** | Thu | 0.2 | PUT | 10:05 | `SENSEX 71100 PE` | ₹90.6 | ₹38.0 | ₹26.6 | -11.4 | **-₹228.00** | STOP_LOSS_HIT |
| **2026-05-07** | Thu | 0.2 | PUT | 09:20 | `SENSEX 77400 PE` | ₹98.4 | ₹38.0 | ₹22.8 | -15.2 | **-₹304.00** | EOD_SQUAREOFF |
