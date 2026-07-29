# Three-Dimensional Option Event Discovery V1

Principal verdict: `NO_OOF_SURVIVOR_IN_THREE_DIMENSIONAL_OPTION_EVENT_FAMILY`

## Boundary

Historical five-minute candle-proxy research only. No paper/live authorization. Execution remains blocked without timestamp-aligned bid/ask/spread evidence.

## OOF survivors

[]

## Holdout survivors

[]

## Best OOF records by PF

```json
[
  {
    "mechanism": "isolated_contract_reclaim",
    "trades": 23,
    "sessions": 12,
    "profit_factor": 2.5486339559698874,
    "mean_return_pct": 3.3398782759503103,
    "median_return_pct": 3.7181818181818205,
    "win_rate": 0.6086956521739131,
    "net_return_pct_sum": 76.81720034685713,
    "remove_top_five_profit_factor": 0.7369312328036002,
    "remove_top_three_profit_factor": 1.1723135233426598,
    "stress_profit_factor": 1.9725145231382764,
    "bootstrap_mean_ci_low": -0.7465687713686253,
    "bootstrap_mean_ci_high": 7.700976426434797,
    "positive_folds": 2,
    "total_folds": 3,
    "positive_halves": 1,
    "total_halves": 2,
    "largest_winner_share": 0.24175065606671242,
    "largest_session_share": 0.3454379490686191,
    "mirror_control": {
      "trades": 23,
      "sessions": 12,
      "profit_factor": 0.31505042098835084,
      "mean_return_pct": -5.9755675628569715,
      "median_return_pct": -5.285185185185179,
      "win_rate": 0.34782608695652173,
      "net_return_pct_sum": -137.43805394571035,
      "remove_top_five_profit_factor": 0.030678300566201445,
      "remove_top_three_profit_factor": 0.08468595022322332,
      "stress_profit_factor": 0.26277943819436894,
      "bootstrap_mean_ci_low": -11.776997693164164,
      "bootstrap_mean_ci_high": -0.4120622420477369,
      "positive_folds": 0,
      "total_folds": 3,
      "positive_halves": 0,
      "total_halves": 2,
      "largest_winner_share": 0.2951942516804627,
      "largest_session_share": 0.5108636581291496
    },
    "delayed_control": {
      "trades": 23,
      "sessions": 12,
      "profit_factor": 0.5307957968232804,
      "mean_return_pct": -3.1000731957217877,
      "median_return_pct": -1.4178294573643435,
      "win_rate": 0.391304347826087,
      "net_return_pct_sum": -71.30168350160112,
      "remove_top_five_profit_factor": 0.0934093381789145,
      "remove_top_three_profit_factor": 0.22051230950823436,
      "stress_profit_factor": 0.4425886574220487,
      "bootstrap_mean_ci_low": -8.181992256158829,
      "bootstrap_mean_ci_high": 1.7966474834029016,
      "positive_folds": 1,
      "total_folds": 3,
      "positive_halves": 0,
      "total_halves": 2,
      "largest_winner_share": 0.22485474294970031,
      "largest_session_share": 0.6164877950820312
    },
    "oof_gate": false
  },
  {
    "mechanism": "near_expiry_3d_repair",
    "trades": 223,
    "sessions": 79,
    "profit_factor": 1.0801878466347132,
    "mean_return_pct": 0.2089468534535816,
    "median_return_pct": 0.3153207198892505,
    "win_rate": 0.5336322869955157,
    "net_return_pct_sum": 46.595148320148695,
    "remove_top_five_profit_factor": 0.9029466408736896,
    "remove_top_three_profit_factor": 0.9668433578621982,
    "stress_profit_factor": 0.7743723573287145,
    "bootstrap_mean_ci_low": -0.7756359911851084,
    "bootstrap_mean_ci_high": 1.1569177408975952,
    "positive_folds": 3,
    "total_folds": 4,
    "positive_halves": 1,
    "total_halves": 2,
    "largest_winner_share": 0.038346871496773606,
    "largest_session_share": 0.09722604450568163,
    "mirror_control": {
      "trades": 223,
      "sessions": 79,
      "profit_factor": 0.6259213182191249,
      "mean_return_pct": -2.295734708437466,
      "median_return_pct": -2.6477707006369338,
      "win_rate": 0.3542600896860987,
      "net_return_pct_sum": -511.9488399815549,
      "remove_top_five_profit_factor": 0.41402555800419677,
      "remove_top_three_profit_factor": 0.4798847238670239,
      "stress_profit_factor": 0.5256003083352665,
      "bootstrap_mean_ci_low": -4.232857083079725,
      "bootstrap_mean_ci_high": -0.19911643115579525,
      "positive_folds": 1,
      "total_folds": 4,
      "positive_halves": 0,
      "total_halves": 2,
      "largest_winner_share": 0.10595273422808311,
      "largest_session_share": 0.22672692882558698
    },
    "delayed_control": {
      "trades": 223,
      "sessions": 79,
      "profit_factor": 0.7269146236976297,
      "mean_return_pct": -0.7476362745533471,
      "median_return_pct": -0.7071428571428531,
      "win_rate": 0.45739910313901344,
      "net_return_pct_sum": -166.72288922539641,
      "remove_top_five_profit_factor": 0.5867419630100675,
      "remove_top_three_profit_factor": 0.6335858455961388,
      "stress_profit_factor": 0.49479152269031434,
      "bootstrap_mean_ci_low": -1.593710211842011,
      "bootstrap_mean_ci_high": 0.10603462647683633,
      "positive_folds": 1,
      "total_folds": 4,
      "positive_halves": 0,
      "total_halves": 2,
      "largest_winner_share": 0.05961157496851757,
      "largest_session_share": 0.09533898551803632
    },
    "oof_gate": false
  },
  {
    "mechanism": "wing_edge_convexity_snapback",
    "trades": 403,
    "sessions": 140,
    "profit_factor": 1.0306515695085974,
    "mean_return_pct": 0.07498025343909352,
    "median_return_pct": -0.00016638935107776698,
    "win_rate": 0.4987593052109181,
    "net_return_pct_sum": 30.217042135954692,
    "remove_top_five_profit_factor": 0.9055464772057722,
    "remove_top_three_profit_factor": 0.9469387672144738,
    "stress_profit_factor": 0.7187590478929359,
    "bootstrap_mean_ci_low": -0.5588736121620864,
    "bootstrap_mean_ci_high": 0.7118945975917909,
    "positive_folds": 3,
    "total_folds": 4,
    "positive_halves": 2,
    "total_halves": 2,
    "largest_winner_share": 0.03861184939612296,
    "largest_session_share": 0.04863784537507281,
    "mirror_control": {
      "trades": 403,
      "sessions": 140,
      "profit_factor": 0.6968286497760204,
      "mean_return_pct": -1.2271274992765633,
      "median_return_pct": -0.7555227794165846,
      "win_rate": 0.42431761786600497,
      "net_return_pct_sum": -494.53238220845503,
      "remove_top_five_profit_factor": 0.5735735962407665,
      "remove_top_three_profit_factor": 0.6070105432259085,
      "stress_profit_factor": 0.536579996421281,
      "bootstrap_mean_ci_low": -2.285831023506946,
      "bootstrap_mean_ci_high": -0.19745203054191757,
      "positive_folds": 0,
      "total_folds": 4,
      "positive_halves": 0,
      "total_halves": 2,
      "largest_winner_share": 0.06767782199947675,
      "largest_session_share": 0.061817415593919366
    },
    "delayed_control": {
      "trades": 403,
      "sessions": 140,
      "profit_factor": 0.9700656243104054,
      "mean_return_pct": -0.0731506540755284,
      "median_return_pct": 0.0652589056187986,
      "win_rate": 0.5086848635235732,
      "net_return_pct_sum": -29.479713592437946,
      "remove_top_five_profit_factor": 0.8162737730089368,
      "remove_top_three_profit_factor": 0.869843573721847,
      "stress_profit_factor": 0.6676120741573252,
      "bootstrap_mean_ci_low": -0.7598789596948947,
      "bootstrap_mean_ci_high": 0.6247039202247672,
      "positive_folds": 2,
      "total_folds": 4,
      "positive_halves": 0,
      "total_halves": 2,
      "largest_winner_share": 0.04573544341683106,
      "largest_session_share": 0.09791823672790538
    },
    "oof_gate": false
  }
]
```
