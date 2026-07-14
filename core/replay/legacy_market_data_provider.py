import json
from dataclasses import dataclass
from typing import Mapping, Optional
from datetime import datetime

from core.tick_store import insert_tick
from core.ohlc_buffer import ohlc_buffer
from core.depth_store import depth_store
from core.time_utils import inject_clock
from core.market_data import get_token_for_symbol

@dataclass(frozen=True)
class RecordedReplayEvent:
    replay_event_id: str
    timestamp: datetime
    instrument_token: int | str
    tradingsymbol: str
    last_price: float
    volume: Optional[float]
    ohlc: Optional[Mapping[str, float]]
    depth: Optional[Mapping[str, object]]
    source: str


class ReplayMarketDataProvider:
    """
    Reads recorded events and publishes them into the live state owners.
    Acts as the official input boundary for the active legacy production pipeline.
    """

    def __init__(self, source_path: str):
        self.source_path = source_path
        self._current_time: Optional[datetime] = None
        self.total_published = 0
        self.rejected = 0
        self.last_published_id = None
        
        # Inject the replay clock into time_utils
        inject_clock(self._get_replay_time)
        
    def _get_replay_time(self) -> datetime:
        if self._current_time is None:
            from core.time_utils import IST_TZ
            return datetime.now(IST_TZ)
        return self._current_time

    def read_events(self):
        """
        Generator that reads the source file and yields RecordedReplayEvent.
        """
        with open(self.source_path, 'r') as f:
            for idx, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                
                tradingsymbol = data.get("tradingsymbol")
                token = data.get("instrument_token") or get_token_for_symbol(tradingsymbol)
                
                if not token or not tradingsymbol:
                    self.rejected += 1
                    continue
                    
                ts_str = data.get("timestamp")
                if not ts_str:
                    self.rejected += 1
                    continue
                
                try:
                    from dateutil.parser import parse
                    ts = parse(ts_str)
                except Exception:
                    self.rejected += 1
                    continue
                
                event = RecordedReplayEvent(
                    replay_event_id=str(data.get("replay_event_id", idx)),
                    timestamp=ts,
                    instrument_token=token,
                    tradingsymbol=tradingsymbol,
                    last_price=float(data.get("last_price", 0.0)),
                    volume=float(data.get("volume", 0.0)) if data.get("volume") is not None else None,
                    ohlc=data.get("ohlc"),
                    depth=data.get("depth"),
                    source=data.get("source", "replay")
                )
                yield event

    def publish(self, event: RecordedReplayEvent) -> bool:
        """
        Advances the injected clock and publishes the event into the 
        authoritative live state stores.
        """
        # 1. Advance the clock
        self._current_time = event.timestamp
        
        token_int = int(event.instrument_token) if event.instrument_token else None
        if token_int is None:
            self.rejected += 1
            return False
            
        ts_epoch = event.timestamp.timestamp()
        
        # 2. Publish to live state owners
        
        # tick_store
        insert_tick(
            ts=ts_epoch,
            token=token_int,
            last_price=event.last_price,
            volume=event.volume,
            oi=None,
        )
        
        # depth_store
        if event.depth:
            depth_store.update(token_int, event.depth)
            
        # ohlc_buffer
        ohlc_buffer.update_tick(
            symbol=event.tradingsymbol,
            price=event.last_price,
            volume=event.volume,
            ts=event.timestamp
        )
        
        self.total_published += 1
        self.last_published_id = event.replay_event_id
        return True
