package com.aixion.tradebotpocket.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Stitch Option 3: Glassmorphic Neo-Fintech (Revolut / Arc)
val NeoFintechBg = Color(0xFF0A0F1D)          // Deep Indigo-Tinted Obsidian
val GlassSurface = Color(0x331E293B)         // Frosted Glass Fill (20% Opacity)
val GlassSurfaceElevated = Color(0x4D2A3B53) // Elevated Glass (30% Opacity)
val GlassBorder = Color(0x33FFFFFF)          // 20% Translucent White Border
val GlassBorderActive = Color(0x6610B981)    // Emerald Glow Border

// Neo-Fintech Glowing Accents
val HaloEmerald = Color(0xFF10B981)          // Growth Halo
val HaloCyan = Color(0xFF38BDF8)             // Fluid Telemetry Cyan
val HaloPurple = Color(0xFF818CF8)           // Arc Velvet Indigo Accent
val HaloAmber = Color(0xFFFBBF24)            // Warm Signal
val HaloRose = Color(0xFFFB7185)             // Drawdown Rose

// Text & Ink
val TextGlassPrimary = Color(0xFFFFFFFF)     // Pure White
val TextGlassSecondary = Color(0xFFCBD5E1)   // Slate 300
val TextGlassMuted = Color(0xFF94A3B8)       // Slate 400

private val GlassmorphicColorScheme = darkColorScheme(
    primary = HaloEmerald,
    secondary = HaloCyan,
    tertiary = HaloPurple,
    background = NeoFintechBg,
    surface = GlassSurface,
    surfaceVariant = GlassSurfaceElevated,
    error = HaloRose,
    onPrimary = Color.Black,
    onBackground = TextGlassPrimary,
    onSurface = TextGlassPrimary,
    outline = GlassBorder
)

@Composable
fun AixionPocketTheme(
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = GlassmorphicColorScheme,
        content = content
    )
}
