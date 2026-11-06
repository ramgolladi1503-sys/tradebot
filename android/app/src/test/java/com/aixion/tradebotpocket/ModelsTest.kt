package com.aixion.tradebotpocket

import com.aixion.tradebotpocket.data.HealthResponse
import com.aixion.tradebotpocket.data.PositionItem
import com.aixion.tradebotpocket.data.PositionsResponse
import com.google.gson.Gson
import org.junit.Assert.*
import org.junit.Test

class ModelsTest {
    private val gson = Gson()

    @Test
    fun testHealthResponseDeserialization() {
        val json = """
            {
                "status": "ONLINE",
                "server_time": "2026-11-06T03:30:00",
                "read_only": true,
                "is_order_action": false,
                "broker_api_called": false,
                "allowed_for_live_execution": false,
                "mac_awake": true,
                "broker_auth_status": "VALID",
                "feed_health": "ACTIVE_LIVE",
                "wal_last_updated": "2026-11-06T03:29:55"
            }
        """.trimIndent()

        val response = gson.fromJson(json, HealthResponse::class.java)
        assertEquals("ONLINE", response.status)
        assertTrue(response.readOnly)
        assertFalse(response.isOrderAction)
        assertFalse(response.brokerApiCalled)
        assertFalse(response.allowedForLiveExecution)
        assertTrue(response.macAwake)
        assertEquals("VALID", response.brokerAuthStatus)
    }

    @Test
    fun testPositionsResponseDeserialization() {
        val json = """
            {
                "timestamp": "2026-11-06T03:30:00",
                "positions": [
                    {
                        "index": "NIFTY",
                        "state": "COOL_OFF",
                        "symbol": null,
                        "direction": null,
                        "entry_price": null,
                        "current_price": null,
                        "unrealized_pnl": 0.0,
                        "quantity": null,
                        "target": null,
                        "stop_loss": null,
                        "trailing_step": null,
                        "persisted_at": "2026-11-05T15:30:00"
                    }
                ],
                "total_realized_pnl": 12450.50,
                "trade_count_today": 4,
                "recent_closed_trades": []
            }
        """.trimIndent()

        val response = gson.fromJson(json, PositionsResponse::class.java)
        assertEquals(1, response.positions.size)
        assertEquals("NIFTY", response.positions[0].index)
        assertEquals(12450.50, response.totalRealizedPnl, 0.01)
        assertEquals(4, response.tradeCountToday)
    }
}
