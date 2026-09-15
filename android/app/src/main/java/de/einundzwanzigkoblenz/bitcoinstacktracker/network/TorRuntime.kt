package de.einundzwanzigkoblenz.bitcoinstacktracker.network

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.os.IBinder
import org.torproject.jni.TorService
import java.net.InetSocketAddress
import java.net.Proxy

/** Owns the in-process TorService binding. No public client gets a proxy until
 * Tor reports an established circuit. */
class TorRuntime(context: Context) {
    private val appContext = context.applicationContext
    @Volatile private var service: TorService? = null
    @Volatile private var bound = false

    data class Snapshot(
        val bound: Boolean,
        val socksPort: Int?,
        val circuitEstablished: Boolean,
        val bootstrapPercent: Int?,
    ) {
        val ready: Boolean get() = bound && socksPort != null && circuitEstablished
    }

    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
            service = (binder as? TorService.LocalBinder)?.service
            bound = service != null
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            service = null
            bound = false
        }
    }

    fun bind(): Boolean {
        if (bound) return true
        TorService.setBroadcastPackageName(appContext.packageName)
        val intent = Intent(appContext, TorService::class.java)
        return appContext.bindService(intent, connection, Context.BIND_AUTO_CREATE).also {
            if (!it) {
                service = null
                bound = false
            }
        }
    }

    fun unbind() {
        if (!bound) return
        runCatching { appContext.unbindService(connection) }
        service = null
        bound = false
    }

    fun snapshot(): Snapshot {
        val tor = service
        if (tor == null) return Snapshot(false, null, false, null)

        val port = runCatching { tor.socksPort }.getOrNull()?.takeIf { it > 0 }
        val circuit = runCatching { tor.getInfo("status/circuit-established") }
            .getOrNull()
            ?.trim() == "1"
        val bootstrap = runCatching { tor.getInfo("status/bootstrap-phase") }
            .getOrNull()
            ?.let(::parseBootstrapPercent)

        return Snapshot(true, port, circuit, bootstrap)
    }

    fun publicSocksProxyOrNull(): Proxy? {
        val state = snapshot()
        if (!state.ready) return null
        val port = state.socksPort ?: return null
        return Proxy(
            Proxy.Type.SOCKS,
            InetSocketAddress.createUnresolved("127.0.0.1", port),
        )
    }

    private fun parseBootstrapPercent(value: String): Int? {
        return Regex("PROGRESS=(\\d{1,3})")
            .find(value)
            ?.groupValues
            ?.getOrNull(1)
            ?.toIntOrNull()
            ?.coerceIn(0, 100)
    }
}
