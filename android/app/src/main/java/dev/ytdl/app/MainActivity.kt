package dev.ytdl.app

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.activity.viewModels
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

private val LightScheme = lightColorScheme(
    primary = Color(0xFF4F46E5),
    onPrimary = Color.White,
    secondaryContainer = Color(0xFFE0E0FF),
    onSecondaryContainer = Color(0xFF1E1B6B),
    surfaceTint = Color(0xFF4F46E5),
)

private val DarkScheme = darkColorScheme(
    primary = Color(0xFF9B95FF),
    onPrimary = Color(0xFF1E1B6B),
    secondaryContainer = Color(0xFF38368F),
    onSecondaryContainer = Color(0xFFE0E0FF),
    background = Color(0xFF14141C),
    surface = Color(0xFF14141C),
    surfaceTint = Color(0xFF9B95FF),
)

class MainActivity : ComponentActivity() {
    private val vm: DownloadViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        takeSharedLink(intent)
        enableEdgeToEdge()
        setContent {
            val dark = when (vm.theme) {
                "Dark" -> true
                "Light" -> false
                else -> isSystemInDarkTheme()
            }
            val view = LocalView.current
            SideEffect {
                // Dark icons on a light status bar and vice versa, following the app theme.
                WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = !dark
            }
            MaterialTheme(colorScheme = if (dark) DarkScheme else LightScheme) {
                Surface(Modifier.fillMaxSize()) { Screen(vm) }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        takeSharedLink(intent)
    }

    private fun takeSharedLink(intent: Intent?) {
        if (intent?.action == Intent.ACTION_SEND) {
            intent.getStringExtra(Intent.EXTRA_TEXT)?.let { vm.url = it.trim() }
        }
    }
}

@Composable
private fun Screen(vm: DownloadViewModel) {
    Column(
        Modifier.fillMaxSize().systemBarsPadding().padding(16.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("ytdl", style = MaterialTheme.typography.headlineMedium)
        OutlinedTextField(
            value = vm.url, onValueChange = { vm.url = it },
            label = { Text("Video link") }, supportingText = { Text("YouTube, Instagram, X/Twitter, Facebook") }, modifier = Modifier.fillMaxWidth(),
        )
        Text("Video format", style = MaterialTheme.typography.labelLarge)
        FormatRow(VIDEO_FORMATS, vm.format) { vm.format = it }
        Text("Audio only", style = MaterialTheme.typography.labelLarge)
        FormatRow(AUDIO_FORMATS, vm.format) { vm.format = it }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Checkbox(vm.playlist, { vm.playlist = it })
            Text("All videos in playlist/post")
        }
        if (!vm.audioOnly) {
            Text("Max quality", style = MaterialTheme.typography.labelLarge)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                QUALITIES.forEach { q ->
                    FilterChip(
                        selected = vm.quality == q, onClick = { vm.quality = q },
                        label = { Text(if (q == "best") q else "${q}p") },
                    )
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (vm.busy) {
                Button(onClick = vm::cancel) { Text("Cancel") }
            } else {
                Button(onClick = vm::start, enabled = vm.ready && vm.url.isNotBlank()) { Text("Download") }
            }
            OutlinedButton(onClick = vm::updateEngine, enabled = vm.ready && !vm.busy) { Text("Update engine") }
        }
        if (vm.busy) LinearProgressIndicator(progress = { vm.progress }, modifier = Modifier.fillMaxWidth())
        Text(vm.status, style = MaterialTheme.typography.bodyMedium)
        Text("Theme", style = MaterialTheme.typography.labelLarge)
        FormatRow(THEMES, vm.theme, vm::chooseTheme)
    }
}

@Composable
private fun FormatRow(options: List<String>, selected: String, onSelect: (String) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        options.forEach { f ->
            FilterChip(selected = selected == f, onClick = { onSelect(f) }, label = { Text(f) })
        }
    }
}
