package com.aixion.tradebotpocket.data

import com.google.gson.annotations.SerializedName

data class HealthResponse(
    @SerializedName("status") val status: String,
    @SerializedName("server_time") val serverTime: String,
    @SerializedName("read_only") val readOnly: Boolean,
    @SerializedName("is_order_action") val isOrderAction: Boolean,
    @SerializedName("broker_api_called") val brokerApiCalled: Boolean,
    @SerializedName("allowed_for_live_execution") val allowedForLiveExecution: Boolean,
    @SerializedName("mac_awake") val macAwake: Boolean,
    @SerializedName("broker_auth_status") val brokerAuthStatus: String,
    @SerializedName("feed_health") val feedHealth: String,
    @SerializedName("wal_last_updated") val walLastUpdated: String?
)

data class PositionItem(
    @SerializedName("index") val index: String,
    @SerializedName("state") val state: String,
    @SerializedName("symbol") val symbol: String?,
    @SerializedName("direction") val direction: String?,
    @SerializedName("entry_price") val entryPrice: Double?,
    @SerializedName("current_price") val currentPrice: Double?,
    @SerializedName("unrealized_pnl") val unrealizedPnl: Double?,
    @SerializedName("quantity") val quantity: Int?,
    @SerializedName("target") val target: Double?,
    @SerializedName("stop_loss") val stopLoss: Double?,
    @SerializedName("trailing_step") val trailingStep: Double?,
    @SerializedName("persisted_at") val persistedAt: String?
)

data class ClosedTradeItem(
    @SerializedName("index") val index: String?,
    @SerializedName("symbol") val symbol: String?,
    @SerializedName("direction") val direction: String?,
    @SerializedName("entry_price") val entryPrice: Double?,
    @SerializedName("exit_price") val exitPrice: Double?,
    @SerializedName("realized_pnl") val realizedPnl: Double?,
    @SerializedName("exit_reason") val exitReason: String?,
    @SerializedName("exit_time") val exitTime: String?
)

data class PositionsResponse(
    @SerializedName("timestamp") val timestamp: String,
    @SerializedName("positions") val positions: List<PositionItem>,
    @SerializedName("total_realized_pnl") val totalRealizedPnl: Double,
    @SerializedName("trade_count_today") val tradeCountToday: Int,
    @SerializedName("recent_closed_trades") val recentClosedTrades: List<ClosedTradeItem>
)

data class MarketResponse(
    @SerializedName("timestamp") val timestamp: String,
    @SerializedName("indices") val indices: Map<String, Any>,
    @SerializedName("feed_status") val feedStatus: String,
    @SerializedName("stale_warning") val staleWarning: Boolean
)

data class SignalsResponse(
    @SerializedName("timestamp") val timestamp: String,
    @SerializedName("event_count") val eventCount: Int,
    @SerializedName("events") val events: List<Map<String, Any>>
)

data class CandlePoint(
    @SerializedName("time") val time: String,
    @SerializedName("open") val open: Double,
    @SerializedName("high") val high: Double,
    @SerializedName("low") val low: Double,
    @SerializedName("close") val close: Double
)

data class ChartResponse(
    @SerializedName("index") val index: String,
    @SerializedName("candles") val candles: List<CandlePoint>,
    @SerializedName("or_high") val orHigh: Double?,
    @SerializedName("or_low") val orLow: Double?,
    @SerializedName("trend_decider") val trendDecider: Double?,
    @SerializedName("rp1_upper") val rp1Upper: Double?,
    @SerializedName("rp2_upper") val rp2Upper: Double?,
    @SerializedName("rp1_lower") val rp1Lower: Double?,
    @SerializedName("rp2_lower") val rp2Lower: Double?,
    @SerializedName("call_strike") val callStrike: Double?,
    @SerializedName("put_strike") val putStrike: Double?,
    @SerializedName("target_strike") val targetStrike: Double?,
    @SerializedName("bias") val bias: String?,
    @SerializedName("current_spot") val currentSpot: Double?
)
