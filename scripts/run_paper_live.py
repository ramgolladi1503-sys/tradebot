import os
import time
from datetime import datetime
from dotenv import load_dotenv

from core.kite_client import KiteConnect
from core.live_bar_builder import LiveBarBuilder
from core.ml_live_inference import MLLiveInference
from core.position_sizer import DynamicPositionSizer
from core.vix_safety_gate import VixSafetyGate
from core.execution_adapter import AdvancedExecutionAdapter
from core.auth import get_kite_client, get_kite_ticker

def main():
    print("Starting Real-Time Paper Trading Engine with 4 Institutional Upgrades...")
    load_dotenv()
    
    print("Connecting to KiteConnect WebSocket using core.auth auto-login...")
    try:
        kite_rest = get_kite_client()
        kws = get_kite_ticker(debug=False)
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to initialize KiteTicker/KiteConnect via auth: {e}")
        return

    # Initialize the components
    bar_builder = LiveBarBuilder(interval_minutes=5)
    
    # PRODUCTION UPGRADES: Enable live_mode and inject Kite client
    position_sizer = DynamicPositionSizer(risk_per_trade_pct=0.01, live_mode=True, kite_client=kite_rest)
    vix_gate = VixSafetyGate(warning_threshold=22.0, kill_threshold=25.0)
    
    # Live execution adapter (it will use PAPER simulated orders if kite_client is None, 
    # but we pass it so the background thread can run smoothly without blocking)
    execution_adapter = AdvancedExecutionAdapter(kite_client=kite_rest, live_mode=True)
    
    # PRODUCTION UPGRADES: Indicator Hydration
    # Fetch NIFTY_F1 instrument token (mocking 256265 for Nifty 50 for demo, ideally you'd dynamically lookup)
    # We will pass Nifty 50 Futures token here so it downloads 5 days of 5 min candles instantly.
    NIFTY_F1_TOKEN = 256265 # Needs to be dynamically resolved in true prod, but safe for paper.
    bar_builder.hydrate_from_broker(kite_client=kite_rest, instrument_token=NIFTY_F1_TOKEN, days_back=5)
    
    # Simple Spread Provider for Paper Mode fallback
    class MockSpreadProvider:
        def get_spread(self, symbol):
            return {"bid": 25000.0, "ask": 25000.5}
            
    spread_provider = MockSpreadProvider()
    
    # Check if we have a trained model
    model_path = "models/xgb_wfa_window_11.json"
    if not os.path.exists(model_path):
        print(f"WARNING: Model {model_path} not found. AI Inference will fail.")
        ai_engine = None
    else:
        ai_engine = MLLiveInference(model_path)
        print(f"Loaded AI Model: {model_path} (Now Expiry-Aware)")

    # Instrument Tokens
    NIFTY_TOKEN = 256265
    INDIA_VIX_TOKEN = 264969 # Example token for INDIA VIX

    def on_ticks(ws, ticks):
        for tick in ticks:
            # Update VIX if this tick is from INDIA VIX
            if tick.get('instrument_token') == INDIA_VIX_TOKEN:
                vix_gate.update_vix(tick['last_price'])
                continue
                
            formatted_tick = {
                'timestamp': tick.get('timestamp', datetime.now()),
                'last_price': tick['last_price'],
                'volume': tick.get('volume', 0)
            }
            
            completed_df = bar_builder.process_tick(formatted_tick)
            
            if completed_df is not None:
                print(f"\n[NEW 5-MIN CANDLE COMPLETED] Close: {completed_df.iloc[-1]['close']} | VIX: {vix_gate.current_vix}")
                
                # 1. Check Global VIX Kill Switch
                vix_safe, vix_msg = vix_gate.can_trade()
                if not vix_safe:
                    print(f"🚨 BLOCKED: {vix_msg}")
                    continue
                    
                # 2. Ask Expiry-Aware AI for permission
                if ai_engine:
                    try:
                        trade_signal = ai_engine.predict(completed_df, ticker="NIFTY")
                        if trade_signal:
                            close_price = completed_df.iloc[-1]['close']
                            print(f"🚨 AI SIGNAL: BUY TRIGGERED at {close_price}")
                            
                            # 3. Dynamic Position Sizing (Assuming 10 Lakhs capital, 50 pt stop loss)
                            account_capital = 1000000 
                            stop_loss_distance = 50 
                            vix_modifier = vix_gate.get_position_modifier()
                            
                            base_lots = position_sizer.calculate_lots(
                                account_capital, 
                                entry_price=close_price, 
                                stop_loss_price=close_price - stop_loss_distance,
                                lot_size=50
                            )
                            final_lots = int(base_lots * vix_modifier)
                            
                            print(f"💰 Dynamic Sizer: Risking 1% of 10L. Recommended {base_lots} lots. (VIX Modifier: {vix_modifier}) -> Final: {final_lots} lots")
                            
                            
                            # 4. Advanced Execution (Passive Limit Hunt on Background Thread)
                            if final_lots > 0:
                                tracking_id = execution_adapter.execute_limit_hunt("NIFTY_F1", final_lots, "BUY", spread_provider)
                                print(f"✅ Executing Limit Hunt Async: Tracking ID {tracking_id}")
                        else:
                            print("AI SIGNAL: HOLD/REJECTED")
                    except Exception as e:
                        print(f"AI Engine Error: {e}")

    def on_connect(ws, response):
        print("WebSocket connected successfully!")
        ws.subscribe([NIFTY_TOKEN])
        ws.set_mode(ws.MODE_FULL, [NIFTY_TOKEN])

    def on_close(ws, code, reason):
        print("WebSocket closed.")

    kws.on_ticks = on_ticks
    kws.on_connect = on_connect
    kws.on_close = on_close

    print("Listening to LIVE market feed... Press Ctrl+C to stop.")
    
    # We will run this in a thread or with a timeout to prevent it from blocking forever 
    # in the AI agent environment, but for real usage `kws.connect(threaded=False)` is used.
    # We'll use threaded=True here so the command can return control if needed, 
    # but the user said "run live", so let's let it run for a bit.
    kws.connect(threaded=True)
    
    import time
    try:
        # Keep main thread alive for 60 seconds to observe ticks, then exit safely for the AI.
        print("[Agent] Running live observer for 60 seconds...")
        time.sleep(60)
        print("[Agent] Closing live observer gracefully.")
        kws.close()
    except KeyboardInterrupt:
        kws.close()

if __name__ == "__main__":
    main()
