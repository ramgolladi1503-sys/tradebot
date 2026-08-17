import time
import threading
import uuid

from typing import Any

from core.observation_execution_guard import assert_execution_allowed

class AdvancedExecutionAdapter:
    def __init__(self, kite_client: Any | None = None, max_chase_retries: int = 3, retry_delay_sec: float = 2.0, live_mode: bool = False) -> None:
        self.kite = kite_client
        self.max_chase_retries = max_chase_retries
        self.retry_delay = retry_delay_sec
        self.live_mode = live_mode
        self.active_threads = []
        
    def execute_limit_hunt(self, symbol: str, quantity: int, transaction_type: str, live_bid_ask_provider) -> str:
        """
        Spawns a background daemon thread to hunt the Bid/Ask spread asynchronously,
        returning an internal tracking ID immediately so the main feed is never blocked.
        """
        assert_execution_allowed("AdvancedExecutionAdapter.execute_limit_hunt")
        internal_id = str(uuid.uuid4())
        
        # Spawn daemon thread to avoid blocking WebSocket
        t = threading.Thread(target=self._hunt_thread, args=(internal_id, symbol, quantity, transaction_type, live_bid_ask_provider))
        t.daemon = True
        t.start()
        
        self.active_threads.append(t)
        return internal_id

    def modify_order(self, *args: Any, **kwargs: Any) -> None:
        assert_execution_allowed("AdvancedExecutionAdapter.modify_order")
        raise NotImplementedError("modify_order is not implemented")

    def cancel_order(self, *args: Any, **kwargs: Any) -> None:
        assert_execution_allowed("AdvancedExecutionAdapter.cancel_order")
        raise NotImplementedError("cancel_order is not implemented")
        
    def _hunt_thread(self, internal_id: str, symbol: str, quantity: int, transaction_type: str, live_bid_ask_provider: Any) -> None:
        retries = 0
        order_id = None
        
        while retries <= self.max_chase_retries:
            try:
                spread = live_bid_ask_provider.get_spread(symbol)
                target_price = spread['bid'] if transaction_type == "BUY" else spread['ask']
                
                if order_id is None:
                    # Place new limit order
                    print(f"[{internal_id}] Placing LIMIT {transaction_type} for {symbol} at {target_price}")
                    if self.live_mode and self.kite:
                        # order_id = self.kite.place_order(variety=self.kite.VARIETY_REGULAR, exchange=self.kite.EXCHANGE_NFO, tradingsymbol=symbol, transaction_type=transaction_type, quantity=quantity, product=self.kite.PRODUCT_NRML, order_type=self.kite.ORDER_TYPE_LIMIT, price=target_price)
                        order_id = f"LIVE_MOCK_{int(time.time())}"
                    else:
                        order_id = f"PAPER_MOCK_{int(time.time())}"
                else:
                    # Modify existing order
                    print(f"[{internal_id}] Modifying LIMIT to chase {symbol} to {target_price}")
                    if self.live_mode and self.kite:
                        # self.kite.modify_order(variety=self.kite.VARIETY_REGULAR, order_id=order_id, order_type=self.kite.ORDER_TYPE_LIMIT, price=target_price)
                        pass
                    
                time.sleep(self.retry_delay)
                
                # Check status
                if self.live_mode and self.kite:
                    # order_history = self.kite.order_history(order_id=order_id)
                    # if order_history[-1]['status'] == 'COMPLETE':
                    #     print(f"[{internal_id}] Order {order_id} FILLED at {target_price}")
                    #     return
                    pass
                else:
                    # Simulated Paper Fill
                    print(f"[{internal_id}] Paper Order {order_id} FILLED at {target_price}")
                    return
                    
            except Exception as e:
                print(f"[{internal_id}] API Error during hunt: {e}")
                
            retries += 1
            
        print(f"[{internal_id}] Order {order_id} failed to fill after {self.max_chase_retries} chases. Cancelling.")
        if self.live_mode and self.kite and order_id:
            try:
                # self.kite.cancel_order(variety=self.kite.VARIETY_REGULAR, order_id=order_id)
                pass
            except Exception as e:
                print(f"[{internal_id}] Failed to cancel order: {e}")
