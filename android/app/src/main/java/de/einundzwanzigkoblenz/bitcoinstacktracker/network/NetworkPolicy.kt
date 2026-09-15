package de.einundzwanzigkoblenz.bitcoinstacktracker.network

import java.net.Inet6Address
import java.net.InetAddress
import java.net.URI

/**
 * Pure routing policy. It must run before any DNS lookup or socket creation.
 *
 * This mirrors the Home Assistant rule: explicitly approved local/private nodes
 * may connect directly; every onion/public destination goes through Tor; public
 * Clearnet additionally requires HTTPS.
 */
object NetworkPolicy {
    enum class Route {
        LOCAL_DIRECT,
        TOR,
    }

    data class Decision(
        val route: Route? = null,
        val blockedReason: String? = null,
    ) {
        val allowed: Boolean get() = route != null && blockedReason == null
    }

    fun decide(targetUrl: String, ownLocalNode: Boolean = false): Decision {
        val uri = try {
            URI(targetUrl.trim())
        } catch (_: Exception) {
            return blocked("Invalid URL")
        }

        val scheme = uri.scheme?.lowercase()
        val host = uri.host?.lowercase()?.trimEnd('.')
        if (scheme !in setOf("http", "https") || host.isNullOrBlank()) {
            return blocked("Only explicit HTTP(S) targets are permitted")
        }
        if (uri.userInfo != null) {
            return blocked("Credentials in target URLs are not permitted")
        }

        if (host.endsWith(".onion")) {
            return Decision(route = Route.TOR)
        }

        val local = isPrivateOrLocalHost(host)
        if (local) {
            return if (ownLocalNode) {
                Decision(route = Route.LOCAL_DIRECT)
            } else {
                blocked("Local/private targets require explicit own-node approval")
            }
        }

        if (scheme != "https") {
            return blocked("Public non-onion targets require HTTPS over Tor")
        }
        return Decision(route = Route.TOR)
    }

    fun isPrivateOrLocalHost(hostValue: String): Boolean {
        val host = hostValue.lowercase().trim().trim('[', ']').trimEnd('.')
        if (host in setOf("localhost", "homeassistant", "supervisor")) return true
        if (host.endsWith(".local") ||
            host.endsWith(".home.arpa") ||
            host.endsWith(".lan") ||
            host.endsWith(".internal")
        ) return true

        parseIpv4(host)?.let { octets ->
            val a = octets[0]
            val b = octets[1]
            return a == 10 ||
                (a == 172 && b in 16..31) ||
                (a == 192 && b == 168) ||
                a == 127 ||
                (a == 169 && b == 254)
        }

        if (host.contains(':')) {
            val address = try {
                InetAddress.getByName(host)
            } catch (_: Exception) {
                return false
            }
            if (address !is Inet6Address) return false
            val bytes = address.address
            val first = bytes[0].toInt() and 0xff
            val second = bytes[1].toInt() and 0xff
            val loopback = bytes.dropLast(1).all { it.toInt() == 0 } && bytes.last().toInt() == 1
            val uniqueLocal = (first and 0xfe) == 0xfc // fc00::/7
            val linkLocal = first == 0xfe && (second and 0xc0) == 0x80 // fe80::/10
            return loopback || uniqueLocal || linkLocal
        }

        return false
    }

    private fun parseIpv4(host: String): IntArray? {
        val parts = host.split('.')
        if (parts.size != 4) return null
        val octets = IntArray(4)
        for (i in parts.indices) {
            if (parts[i].isEmpty() || parts[i].any { !it.isDigit() }) return null
            val value = parts[i].toIntOrNull() ?: return null
            if (value !in 0..255) return null
            octets[i] = value
        }
        return octets
    }

    private fun blocked(reason: String) = Decision(blockedReason = reason)
}
