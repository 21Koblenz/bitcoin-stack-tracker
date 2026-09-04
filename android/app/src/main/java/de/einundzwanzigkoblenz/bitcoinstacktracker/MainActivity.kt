package de.einundzwanzigkoblenz.bitcoinstacktracker

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import de.einundzwanzigkoblenz.bitcoinstacktracker.network.TorRuntime
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    TrackerHome()
                }
            }
        }
    }
}

@Composable
private fun TrackerHome() {
    val context = LocalContext.current
    val torRuntime = remember { TorRuntime(context) }
    var tor by remember { mutableStateOf(torRuntime.snapshot()) }

    DisposableEffect(torRuntime) {
        torRuntime.bind()
        onDispose { torRuntime.unbind() }
    }

    LaunchedEffect(torRuntime) {
        while (isActive) {
            tor = torRuntime.snapshot()
            delay(1_000)
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Image(
                painter = painterResource(R.drawable.bitcoin_stack_tracker_logo),
                contentDescription = null,
                modifier = Modifier.size(58.dp),
            )
            Column {
                Text(
                    text = "Bitcoin Stack Tracker",
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                )
                Text("Local first · Bitcoin only · Tor first")
            }
        }

        SecurityCard(tor)

        Text(
            text = "Android-Port",
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold,
        )
        FeatureCard("Übersicht", "Stack, Portfolios, Performance und Marktübersicht")
        FeatureCard("Buchungen & FIFO", "Käufe, Verkäufe, Einnahmen, Ausgaben und Gebühren")
        FeatureCard("Sats Sentinel", "Watch-only Überwachung ohne Seed oder Private Keys")
        FeatureCard("Ziele", "Stacking-Ziele und Fortschritt")
        FeatureCard("Analyse", "Charts, Marktmodell, TWR, XIRR, CAGR und Drawdown")

        Text(
            text = "Die Oberfläche ist absichtlich noch ein Grundgerüst. Netzwerk- und Verschlüsselungsgrenzen werden vor dem Feature-Port festgelegt.",
            style = MaterialTheme.typography.bodySmall,
        )
    }
}

@Composable
private fun SecurityCard(tor: TorRuntime.Snapshot) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(7.dp),
        ) {
            Text(
                text = "Privatsphäre & Netzwerk",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
            Text("Tor: ${torLabel(tor)}")
            Text("Direkter öffentlicher Clearnet-Fallback: AUS")
            Text("Öffentliche Ziele: HTTPS über Tor")
            Text("Eigene lokale Node: nur nach expliziter Freigabe direkt")
            Text("Seed / Private Keys / xprv: nicht Bestandteil der App")
        }
    }
}

private fun torLabel(tor: TorRuntime.Snapshot): String = when {
    tor.ready -> "AKTIV · SOCKS ${tor.socksPort} · Circuit bereit"
    tor.bootstrapPercent != null -> "STARTET · ${tor.bootstrapPercent}%"
    tor.bound -> "STARTET"
    else -> "NICHT VERBUNDEN"
}

@Composable
private fun FeatureCard(title: String, description: String) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(title, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(4.dp))
            Text(description, style = MaterialTheme.typography.bodyMedium)
        }
    }
}
