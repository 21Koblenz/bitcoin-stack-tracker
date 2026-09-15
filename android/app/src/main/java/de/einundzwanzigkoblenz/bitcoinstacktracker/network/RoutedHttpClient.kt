package de.einundzwanzigkoblenz.bitcoinstacktracker.network

import okhttp3.Call
import okhttp3.Dns
import okhttp3.OkHttpClient
import okhttp3.Request
import java.net.InetAddress
import java.net.Proxy
import java.net.UnknownHostException
import java.util.concurrent.TimeUnit

class RoutedHttpClient(private val torRuntime: TorRuntime) {
    class RouteBlockedException(message: String) : IllegalStateException(message)
    class TorUnavailableException : IllegalStateException("Tor is not ready; public request blocked")

    fun get(targetUrl: String, ownLocalNode: Boolean = false): Call {
        val decision = NetworkPolicy.decide(targetUrl, ownLocalNode)
        if (!decision.allowed) {
            throw RouteBlockedException(decision.blockedReason ?: "Network route blocked")
        }

        val request = Request.Builder()
            .url(targetUrl)
            .get()
            .build()

        val client = when (decision.route) {
            NetworkPolicy.Route.TOR -> torClient()
            NetworkPolicy.Route.LOCAL_DIRECT -> localClient()
            null -> throw RouteBlockedException("Network route blocked")
        }
        return client.newCall(request)
    }

    private fun torClient(): OkHttpClient {
        val socks = torRuntime.publicSocksProxyOrNull() ?: throw TorUnavailableException()
        return baseBuilder()
            // A fixed explicit proxy means OkHttp has no direct fallback route.
            .proxy(socks)
            // SOCKS routing must never ask Android/system DNS for a public target.
            .dns(object : Dns {
                override fun lookup(hostname: String): List<InetAddress> {
                    throw UnknownHostException("Local DNS is forbidden for Tor target: $hostname")
                }
            })
            .build()
    }

    private fun localClient(): OkHttpClient {
        return baseBuilder()
            .proxy(Proxy.NO_PROXY)
            .dns(PrivateOnlyDns)
            .build()
    }

    private fun baseBuilder(): OkHttpClient.Builder = OkHttpClient.Builder()
        .followRedirects(false)
        .followSslRedirects(false)
        .retryOnConnectionFailure(false)
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)

    private object PrivateOnlyDns : Dns {
        override fun lookup(hostname: String): List<InetAddress> {
            if (!NetworkPolicy.isPrivateOrLocalHost(hostname)) {
                throw UnknownHostException("Direct DNS blocked for non-local host: $hostname")
            }
            val addresses = InetAddress.getAllByName(hostname).toList()
            if (addresses.isEmpty()) {
                throw UnknownHostException("No local addresses for $hostname")
            }
            if (addresses.any { address ->
                    val literal = address.hostAddress?.substringBefore('%').orEmpty()
                    !NetworkPolicy.isPrivateOrLocalHost(literal)
                }
            ) {
                throw UnknownHostException("Local target resolved outside private networks: $hostname")
            }
            return addresses
        }
    }
}
