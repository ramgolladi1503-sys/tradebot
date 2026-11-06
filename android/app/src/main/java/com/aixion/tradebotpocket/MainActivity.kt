package com.aixion.tradebotpocket

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.animation.*
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.aixion.tradebotpocket.data.*
import com.aixion.tradebotpocket.ui.theme.*
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

sealed class UiState {
    object Loading : UiState()
    data class Success(
        val health: HealthResponse,
        val positions: PositionsResponse,
        val market: MarketResponse,
        val chart: ChartResponse?
    ) : UiState()
    data class Error(val message: String) : UiState()
}

enum class ScreenTab {
    DASHBOARD,
    CHARTS,
    HISTORY
}

class MainViewModel : ViewModel() {
    private val _uiState = MutableStateFlow<UiState>(UiState.Loading)
    val uiState: StateFlow<UiState> = _uiState

    var currentTab by mutableStateOf(ScreenTab.DASHBOARD)
    var selectedIndex by mutableStateOf("NIFTY")

    var serverUrl by mutableStateOf("http://100.68.131.88:8765")
    var apiKey by mutableStateOf("aixion-pocket-secret-key-v1")
    var autoRefresh by mutableStateOf(true)

    init {
        startPolling()
    }

    fun refreshData() {
        viewModelScope.launch {
            try {
                val api = ApiClient.getService(serverUrl)
                val health = api.getHealth(apiKey)
                val positions = api.getPositions(apiKey)
                val market = api.getMarket(apiKey)
                val chart = try {
                    api.getChart(apiKey, selectedIndex)
                } catch (e: Exception) {
                    null
                }
                _uiState.value = UiState.Success(health, positions, market, chart)
            } catch (e: Exception) {
                _uiState.value = UiState.Error(e.localizedMessage ?: "Connection failure to companion service.")
            }
        }
    }

    private fun startPolling() {
        viewModelScope.launch {
            while (true) {
                if (autoRefresh) {
                    refreshData()
                }
                delay(2500)
            }
        }
    }
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            AixionPocketTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    MainNavigationScaffold()
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainNavigationScaffold(viewModel: MainViewModel = viewModel()) {
    val uiState by viewModel.uiState.collectAsState()
    var showConfigDialog by remember { mutableStateOf(false) }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(NeoFintechBg)
    ) {
        // Glowing Neo-Fintech Background Orbs
        Box(
            modifier = Modifier
                .size(260.dp)
                .offset(x = (-40).dp, y = (-20).dp)
                .clip(CircleShape)
                .background(Brush.radialGradient(listOf(Color(0x3310B981), Color.Transparent)))
        )
        Box(
            modifier = Modifier
                .size(320.dp)
                .align(Alignment.TopEnd)
                .offset(x = 80.dp, y = 60.dp)
                .clip(CircleShape)
                .background(Brush.radialGradient(listOf(Color(0x2638BDF8), Color.Transparent)))
        )

        Scaffold(
            containerColor = Color.Transparent,
            topBar = {
                TopAppBar(
                    title = {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Surface(
                                shape = RoundedCornerShape(10.dp),
                                color = GlassSurfaceElevated,
                                border = BorderStroke(1.dp, GlassBorder),
                                modifier = Modifier.size(36.dp)
                            ) {
                                Box(contentAlignment = Alignment.Center) {
                                    Icon(
                                        Icons.Default.Bolt,
                                        contentDescription = "Logo",
                                        tint = HaloEmerald,
                                        modifier = Modifier.size(20.dp)
                                    )
                                }
                            }
                            Spacer(modifier = Modifier.width(10.dp))
                            Column {
                                Text(
                                    "Aixion Sentinel Live",
                                    fontSize = 16.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = TextGlassPrimary
                                )
                                Text(
                                    "PR #987 OptionMate • Tailscale",
                                    fontSize = 9.sp,
                                    color = TextGlassMuted
                                )
                            }
                        }
                    },
                    actions = {
                        IconButton(onClick = { viewModel.refreshData() }) {
                            Icon(Icons.Default.Refresh, contentDescription = "Refresh", tint = TextGlassSecondary)
                        }
                        Surface(
                            shape = CircleShape,
                            color = GlassSurfaceElevated,
                            border = BorderStroke(1.dp, GlassBorder),
                            modifier = Modifier.padding(end = 12.dp)
                        ) {
                            TextButton(
                                onClick = { showConfigDialog = true },
                                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 2.dp)
                            ) {
                                Text("HOST", color = HaloCyan, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                            }
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.Transparent)
                )
            },
            bottomBar = {
                NavigationBar(
                    containerColor = Color(0xD90A0F1D),
                    tonalElevation = 8.dp
                ) {
                    NavigationBarItem(
                        selected = viewModel.currentTab == ScreenTab.DASHBOARD,
                        onClick = { viewModel.currentTab = ScreenTab.DASHBOARD },
                        icon = { Icon(Icons.Default.Dashboard, contentDescription = "Live APM") },
                        label = { Text("Live APM", fontSize = 11.sp) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = HaloEmerald,
                            selectedTextColor = HaloEmerald,
                            indicatorColor = Color(0x3310B981),
                            unselectedIconColor = TextGlassMuted,
                            unselectedTextColor = TextGlassMuted
                        )
                    )
                    NavigationBarItem(
                        selected = viewModel.currentTab == ScreenTab.CHARTS,
                        onClick = { viewModel.currentTab = ScreenTab.CHARTS },
                        icon = { Icon(Icons.Default.ShowChart, contentDescription = "Sentinel Chart") },
                        label = { Text("Live Charts", fontSize = 11.sp) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = HaloCyan,
                            selectedTextColor = HaloCyan,
                            indicatorColor = Color(0x3338BDF8),
                            unselectedIconColor = TextGlassMuted,
                            unselectedTextColor = TextGlassMuted
                        )
                    )
                    NavigationBarItem(
                        selected = viewModel.currentTab == ScreenTab.HISTORY,
                        onClick = { viewModel.currentTab = ScreenTab.HISTORY },
                        icon = { Icon(Icons.Default.History, contentDescription = "History") },
                        label = { Text("Trades", fontSize = 11.sp) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = HaloPurple,
                            selectedTextColor = HaloPurple,
                            indicatorColor = Color(0x33818CF8),
                            unselectedIconColor = TextGlassMuted,
                            unselectedTextColor = TextGlassMuted
                        )
                    )
                }
            }
        ) { padding ->
            Box(
                modifier = Modifier
                    .padding(padding)
                    .fillMaxSize()
            ) {
                when (val state = uiState) {
                    is UiState.Loading -> {
                        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator(color = HaloEmerald, strokeWidth = 2.dp)
                        }
                    }
                    is UiState.Error -> {
                        Column(
                            modifier = Modifier.fillMaxSize().padding(24.dp),
                            verticalArrangement = Arrangement.Center,
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            Surface(
                                shape = RoundedCornerShape(20.dp),
                                color = GlassSurfaceElevated,
                                border = BorderStroke(1.dp, GlassBorder),
                                modifier = Modifier.padding(16.dp)
                            ) {
                                Column(modifier = Modifier.padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                                    Icon(Icons.Default.CloudOff, contentDescription = "Error", tint = HaloRose, modifier = Modifier.size(44.dp))
                                    Spacer(modifier = Modifier.height(14.dp))
                                    Text("DISCONNECTED", color = HaloRose, fontWeight = FontWeight.Black, fontSize = 15.sp, letterSpacing = 1.sp)
                                    Spacer(modifier = Modifier.height(6.dp))
                                    Text(state.message, color = TextGlassMuted, fontSize = 11.sp, fontFamily = FontFamily.Monospace)
                                    Spacer(modifier = Modifier.height(18.dp))
                                    Button(
                                        onClick = { viewModel.refreshData() },
                                        colors = ButtonDefaults.buttonColors(containerColor = HaloEmerald),
                                        shape = CircleShape
                                    ) {
                                        Text("Reconnect", color = Color.Black, fontWeight = FontWeight.Bold)
                                    }
                                }
                            }
                        }
                    }
                    is UiState.Success -> {
                        when (viewModel.currentTab) {
                            ScreenTab.DASHBOARD -> DashboardTabContent(state.health, state.positions)
                            ScreenTab.CHARTS -> ChartsTabContent(state.chart, viewModel.selectedIndex) {
                                viewModel.selectedIndex = it
                                viewModel.refreshData()
                            }
                            ScreenTab.HISTORY -> HistoryTabContent(state.positions)
                        }
                    }
                }
            }

            if (showConfigDialog) {
                AlertDialog(
                    onDismissRequest = { showConfigDialog = false },
                    containerColor = Color(0xFF1E293B),
                    title = { Text("Companion Connection", color = TextGlassPrimary) },
                    text = {
                        Column {
                            OutlinedTextField(
                                value = viewModel.serverUrl,
                                onValueChange = { viewModel.serverUrl = it },
                                label = { Text("Tailscale Endpoint URL") },
                                singleLine = true
                            )
                            Spacer(modifier = Modifier.height(12.dp))
                            OutlinedTextField(
                                value = viewModel.apiKey,
                                onValueChange = { viewModel.apiKey = it },
                                label = { Text("Security Header Key") },
                                singleLine = true
                            )
                        }
                    },
                    confirmButton = {
                        Button(
                            onClick = {
                                showConfigDialog = false
                                viewModel.refreshData()
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = HaloEmerald),
                            shape = CircleShape
                        ) {
                            Text("Connect", color = Color.Black, fontWeight = FontWeight.Bold)
                        }
                    },
                    dismissButton = {
                        TextButton(onClick = { showConfigDialog = false }) {
                            Text("Cancel", color = TextGlassSecondary)
                        }
                    }
                )
            }
        }
    }
}

// ----------------- TAB 1: LIVE DASHBOARD & APM -----------------

@Composable
fun DashboardTabContent(health: HealthResponse, positions: PositionsResponse) {
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        item {
            Spacer(modifier = Modifier.height(4.dp))
            GlassmorphicHeroCard(positions.totalRealizedPnl, positions.tradeCountToday)
        }
        item {
            GlassTelemetryChips(health)
        }
        item {
            SectionPillHeader("LIVE RUNNERS IN FLIGHT", positions.positions.size.toString())
        }
        items(positions.positions) { pos ->
            GlassPositionCard(pos)
        }
        item {
            Spacer(modifier = Modifier.height(20.dp))
        }
    }
}

// ----------------- TAB 2: LIVE SENTINEL CHARTS -----------------

@Composable
fun ChartsTabContent(chart: ChartResponse?, selectedIndex: String, onSelectIndex: (String) -> Unit) {
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        item {
            Spacer(modifier = Modifier.height(4.dp))
            // Index Selector Chips
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("NIFTY", "SENSEX", "BANKNIFTY").forEach { idx ->
                    val isSel = idx == selectedIndex
                    Surface(
                        shape = CircleShape,
                        color = if (isSel) Color(0x3338BDF8) else GlassSurfaceElevated,
                        border = BorderStroke(1.dp, if (isSel) HaloCyan else GlassBorder),
                        modifier = Modifier.weight(1f)
                    ) {
                        TextButton(onClick = { onSelectIndex(idx) }) {
                            Text(idx, fontSize = 12.sp, fontWeight = FontWeight.Bold, color = if (isSel) HaloCyan else TextGlassSecondary)
                        }
                    }
                }
            }
        }

        item {
            if (chart != null) {
                SentinelInteractiveChartCard(chart)
            } else {
                Surface(
                    shape = RoundedCornerShape(20.dp),
                    color = GlassSurfaceElevated,
                    border = BorderStroke(1.dp, GlassBorder),
                    modifier = Modifier.fillMaxWidth().height(260.dp)
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text("Loading 1-min live candles...", color = TextGlassMuted, fontSize = 12.sp)
                    }
                }
            }
        }

        item {
            if (chart != null) {
                DrawnLevelsCard(chart)
            }
        }

        item {
            Spacer(modifier = Modifier.height(20.dp))
        }
    }
}

@Composable
fun SentinelInteractiveChartCard(chart: ChartResponse) {
    Surface(
        shape = RoundedCornerShape(24.dp),
        color = GlassSurfaceElevated,
        border = BorderStroke(1.dp, GlassBorder),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(18.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        "${chart.index} (1m Live)",
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Black,
                        color = TextGlassPrimary
                    )
                    Text(
                        "Spot: ₹${String.format("%,.2f", chart.currentSpot ?: 0.0)}",
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        fontFamily = FontFamily.Monospace,
                        color = HaloCyan
                    )
                }

                Surface(
                    shape = CircleShape,
                    color = if (chart.bias == "BULL") Color(0x3310B981) else Color(0x33F43F5E),
                    border = BorderStroke(1.dp, if (chart.bias == "BULL") Color(0x4D10B981) else Color(0x4DF43F5E))
                ) {
                    Text(
                        "BIAS: ${chart.bias ?: "NEUTRAL"}",
                        fontSize = 9.sp,
                        fontWeight = FontWeight.ExtraBold,
                        color = if (chart.bias == "BULL") HaloEmerald else HaloRose,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Canvas drawing 1m Candlestick Chart + Drawn Sentinel Lines
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(220.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(Color(0x80050811))
            ) {
                CandlestickCanvas(chart)
            }
        }
    }
}

@Composable
fun CandlestickCanvas(chart: ChartResponse) {
    val candles = chart.candles
    if (candles.isEmpty()) return

    Canvas(modifier = Modifier.fillMaxSize().padding(10.dp)) {
        val minPrice = candles.minOf { it.low } - 20.0
        val maxPrice = candles.maxOf { it.high } + 20.0
        val priceRange = maxPrice - minPrice

        val width = size.width
        val height = size.height

        fun priceToY(price: Double): Float {
            return (height - ((price - minPrice) / priceRange * height)).toFloat()
        }

        // Draw Sentinel Horizontal Levels (TD, RP1, OR High/Low)
        chart.trend_decider()?.let { td ->
            val y = priceToY(td)
            drawLine(
                color = Color(0xFF38BDF8),
                start = Offset(0f, y),
                end = Offset(width, y),
                strokeWidth = 2f,
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 10f), 0f)
            )
        }
        chart.or_high()?.let { orH ->
            val y = priceToY(orH)
            drawLine(
                color = Color(0xFF10B981),
                start = Offset(0f, y),
                end = Offset(width, y),
                strokeWidth = 1.5f,
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 6f), 0f)
            )
        }
        chart.or_low()?.let { orL ->
            val y = priceToY(orL)
            drawLine(
                color = Color(0xFFF43F5E),
                start = Offset(0f, y),
                end = Offset(width, y),
                strokeWidth = 1.5f,
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 6f), 0f)
            )
        }

        // Draw Candlesticks
        val barWidth = width / candles.size
        candles.forEachIndexed { i, c ->
            val x = i * barWidth + barWidth / 2f
            val isGreen = c.close >= c.open
            val color = if (isGreen) Color(0xFF10B981) else Color(0xFFF43F5E)

            // Wick
            drawLine(
                color = color,
                start = Offset(x, priceToY(c.high)),
                end = Offset(x, priceToY(c.low)),
                strokeWidth = 1.5f
            )

            // Body
            val top = priceToY(maxOf(c.open, c.close))
            val bottom = priceToY(minOf(c.open, c.close))
            val bodyHeight = maxOf(2f, bottom - top)

            drawRect(
                color = color,
                topLeft = Offset(x - barWidth * 0.35f, top),
                size = Size(barWidth * 0.7f, bodyHeight)
            )
        }
    }
}

fun ChartResponse.trend_decider(): Double? = this.trendDecider
fun ChartResponse.or_high(): Double? = this.orHigh
fun ChartResponse.or_low(): Double? = this.orLow

@Composable
fun DrawnLevelsCard(chart: ChartResponse) {
    Surface(
        shape = RoundedCornerShape(20.dp),
        color = GlassSurfaceElevated,
        border = BorderStroke(1.dp, GlassBorder),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(18.dp)) {
            Text(
                "SENTINEL OPTIONMATE LEVELS",
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 1.sp,
                color = TextGlassSecondary
            )
            Spacer(modifier = Modifier.height(12.dp))
            LevelRow("Trend Decider (TD)", "₹${chart.trendDecider ?: 0.0}", HaloCyan)
            Divider(color = GlassBorder, modifier = Modifier.padding(vertical = 8.dp))
            LevelRow("RP1 Upper (Reversal 1)", "₹${chart.rp1Upper ?: 0.0}", HaloAmber)
            Divider(color = GlassBorder, modifier = Modifier.padding(vertical = 8.dp))
            LevelRow("RP1 Lower (Reversal 1)", "₹${chart.rp1Lower ?: 0.0}", HaloEmerald)
            Divider(color = GlassBorder, modifier = Modifier.padding(vertical = 8.dp))
            LevelRow("Target Slingshot Strike", "₹${chart.targetStrike ?: 0.0}", HaloPurple)
        }
    }
}

@Composable
fun LevelRow(label: String, value: String, accent: Color) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                modifier = Modifier
                    .size(6.dp)
                    .clip(CircleShape)
                    .background(accent)
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text(label, fontSize = 12.sp, color = TextGlassSecondary)
        }
        Text(value, fontSize = 12.sp, fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace, color = TextGlassPrimary)
    }
}

// ----------------- TAB 3: HISTORICAL TRADES TIMELINE -----------------

@Composable
fun HistoryTabContent(positions: PositionsResponse) {
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        item {
            Spacer(modifier = Modifier.height(4.dp))
            SectionPillHeader("ALL EXECUTED TRADES", positions.recentClosedTrades.size.toString())
        }
        items(positions.recentClosedTrades) { trade ->
            GlassClosedTradeCard(trade)
        }
        item {
            Spacer(modifier = Modifier.height(20.dp))
        }
    }
}

// ----------------- REUSABLE COMPONENTS -----------------

@Composable
fun SectionPillHeader(title: String, countBadge: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = title,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = 1.sp,
            color = TextGlassSecondary
        )
        Surface(
            shape = CircleShape,
            color = GlassSurfaceElevated,
            border = BorderStroke(1.dp, GlassBorder)
        ) {
            Text(
                countBadge,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
                color = HaloCyan,
                modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp)
            )
        }
    }
}

@Composable
fun GlassmorphicHeroCard(totalPnl: Double, tradeCount: Int) {
    val isPositive = totalPnl >= 0
    val pnlColor = if (isPositive) HaloEmerald else HaloRose

    Surface(
        shape = RoundedCornerShape(24.dp),
        color = GlassSurfaceElevated,
        border = BorderStroke(1.dp, GlassBorder),
        modifier = Modifier.fillMaxWidth()
    ) {
        Box(
            modifier = Modifier
                .background(
                    Brush.radialGradient(
                        colors = listOf(
                            if (isPositive) Color(0x3D10B981) else Color(0x3DF43F5E),
                            Color.Transparent
                        )
                    )
                )
                .padding(24.dp)
        ) {
            Column {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        "NET REALIZED P&L TODAY",
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 1.sp,
                        color = TextGlassSecondary
                    )
                    Surface(
                        shape = CircleShape,
                        color = Color(0x3310B981),
                        border = BorderStroke(1.dp, Color(0x4D10B981))
                    ) {
                        Text(
                            "LIVE APM",
                            fontSize = 9.sp,
                            fontWeight = FontWeight.ExtraBold,
                            color = HaloEmerald,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
                        )
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                Text(
                    text = "${if (isPositive) "+" else ""}₹${String.format("%,.2f", totalPnl)}",
                    fontSize = 36.sp,
                    fontWeight = FontWeight.Black,
                    fontFamily = FontFamily.Monospace,
                    color = pnlColor,
                    letterSpacing = (-1).sp
                )

                Spacer(modifier = Modifier.height(8.dp))

                Text(
                    "$tradeCount Trades Completed in Today's Session",
                    fontSize = 12.sp,
                    color = TextGlassMuted
                )
            }
        }
    }
}

@Composable
fun GlassTelemetryChips(health: HealthResponse) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        GlassChip(
            modifier = Modifier.weight(1f),
            label = "BROKER",
            value = health.brokerAuthStatus,
            accent = if (health.brokerAuthStatus == "VALID") HaloEmerald else HaloAmber
        )
        GlassChip(
            modifier = Modifier.weight(1f),
            label = "FEED",
            value = health.feedHealth.replace("_", " "),
            accent = HaloCyan
        )
        GlassChip(
            modifier = Modifier.weight(1f),
            label = "SAFETY",
            value = "READ-ONLY",
            accent = HaloPurple
        )
    }
}

@Composable
fun GlassChip(modifier: Modifier, label: String, value: String, accent: Color) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        color = GlassSurfaceElevated,
        border = BorderStroke(1.dp, GlassBorder)
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
            horizontalAlignment = Alignment.Start
        ) {
            Text(label, fontSize = 8.sp, fontWeight = FontWeight.Bold, color = TextGlassMuted, letterSpacing = 0.5.sp)
            Spacer(modifier = Modifier.height(4.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(6.dp)
                        .clip(CircleShape)
                        .background(accent)
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text(
                    value,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold,
                    color = TextGlassPrimary,
                    maxLines = 1
                )
            }
        }
    }
}

@Composable
fun GlassPositionCard(pos: PositionItem) {
    val isInPosition = pos.state == "IN_POSITION"
    val accentColor = if (isInPosition) HaloEmerald else HaloAmber

    Surface(
        shape = RoundedCornerShape(20.dp),
        color = GlassSurfaceElevated,
        border = BorderStroke(1.dp, if (isInPosition) GlassBorderActive else GlassBorder),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(18.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        pos.index,
                        fontWeight = FontWeight.Black,
                        fontSize = 17.sp,
                        color = TextGlassPrimary
                    )
                    if (pos.direction != null) {
                        Spacer(modifier = Modifier.width(8.dp))
                        Surface(
                            shape = CircleShape,
                            color = if (pos.direction == "CE") Color(0x3310B981) else Color(0x33F43F5E),
                            border = BorderStroke(1.dp, if (pos.direction == "CE") Color(0x4D10B981) else Color(0x4DF43F5E))
                        ) {
                            Text(
                                pos.direction,
                                fontSize = 10.sp,
                                fontWeight = FontWeight.ExtraBold,
                                color = if (pos.direction == "CE") HaloEmerald else HaloRose,
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp)
                            )
                        }
                    }
                }

                Surface(
                    shape = CircleShape,
                    color = Color(0x26FFFFFF),
                    border = BorderStroke(1.dp, GlassBorder)
                ) {
                    Text(
                        pos.state,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Bold,
                        color = accentColor,
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp)
                    )
                }
            }

            if (pos.symbol != null) {
                Spacer(modifier = Modifier.height(10.dp))
                Text(
                    pos.symbol,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                    color = TextGlassPrimary
                )
                Spacer(modifier = Modifier.height(12.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    GlassMetricColumn("ENTRY", "₹${pos.entryPrice ?: 0.0}")
                    GlassMetricColumn("LTP", "₹${pos.currentPrice ?: 0.0}")
                    GlassMetricColumn("STOP", "₹${pos.stopLoss ?: 0.0}")
                    GlassMetricColumn("QTY", "${pos.quantity ?: 0}")
                }
            } else {
                Spacer(modifier = Modifier.height(6.dp))
                Text(
                    "No active risk in flight • Standby trigger armed",
                    fontSize = 12.sp,
                    color = TextGlassMuted
                )
            }
        }
    }
}

@Composable
fun GlassClosedTradeCard(trade: ClosedTradeItem) {
    val pnl = trade.realizedPnl ?: 0.0
    val isProfit = pnl >= 0
    val pnlColor = if (isProfit) HaloEmerald else HaloRose

    Surface(
        shape = RoundedCornerShape(18.dp),
        color = GlassSurfaceElevated,
        border = BorderStroke(1.dp, GlassBorder),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        trade.symbol ?: (trade.index ?: "TRADE"),
                        fontWeight = FontWeight.Bold,
                        fontSize = 13.sp,
                        color = TextGlassPrimary
                    )
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        "Exit: ${trade.exitTime?.take(8) ?: "--:--"} • ${trade.exitReason ?: "EXIT"}",
                        fontSize = 10.sp,
                        color = TextGlassMuted
                    )
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        "${if (isProfit) "+" else ""}₹${String.format("%,.2f", pnl)}",
                        fontWeight = FontWeight.Black,
                        fontFamily = FontFamily.Monospace,
                        fontSize = 16.sp,
                        color = pnlColor
                    )
                    Text(
                        "₹${trade.entryPrice ?: 0.0} → ₹${trade.exitPrice ?: 0.0}",
                        fontSize = 10.sp,
                        color = TextGlassSecondary,
                        fontFamily = FontFamily.Monospace
                    )
                }
            }
        }
    }
}

@Composable
fun GlassMetricColumn(label: String, value: String) {
    Column {
        Text(label, fontSize = 9.sp, fontWeight = FontWeight.Bold, color = TextGlassMuted)
        Text(
            value,
            fontSize = 12.sp,
            fontWeight = FontWeight.Bold,
            fontFamily = FontFamily.Monospace,
            color = TextGlassPrimary
        )
    }
}
