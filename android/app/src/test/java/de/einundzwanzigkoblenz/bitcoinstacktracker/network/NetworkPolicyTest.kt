package de.einundzwanzigkoblenz.bitcoinstacktracker.network

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NetworkPolicyTest {
    @Test
    fun publicHttpsUsesTor() {
        val decision = NetworkPolicy.decide("https://mempool.space/api/blocks/tip/height")
        assertTrue(decision.allowed)
        assertEquals(NetworkPolicy.Route.TOR, decision.route)
    }

    @Test
    fun publicHttpIsBlockedEvenWhenTorExists() {
        val decision = NetworkPolicy.decide("http://example.com/data")
        assertFalse(decision.allowed)
    }

    @Test
    fun onionHttpUsesTor() {
        val decision = NetworkPolicy.decide("http://exampleexampleexampleexampleexampleexampleexampleexample.onion/api")
        assertTrue(decision.allowed)
        assertEquals(NetworkPolicy.Route.TOR, decision.route)
    }

    @Test
    fun ownPrivateIpv4MayUseLan() {
        val decision = NetworkPolicy.decide("https://192.168.1.20:3006/api", ownLocalNode = true)
        assertTrue(decision.allowed)
        assertEquals(NetworkPolicy.Route.LOCAL_DIRECT, decision.route)
    }

    @Test
    fun privateIpv4WithoutOwnNodeApprovalIsBlocked() {
        val decision = NetworkPolicy.decide("https://10.21.0.5/api")
        assertFalse(decision.allowed)
    }

    @Test
    fun ownHomeArpaMayUseLan() {
        val decision = NetworkPolicy.decide("https://mempool.home.arpa/api", ownLocalNode = true)
        assertEquals(NetworkPolicy.Route.LOCAL_DIRECT, decision.route)
    }

    @Test
    fun credentialsInUrlAreBlocked() {
        val decision = NetworkPolicy.decide("https://user:password@example.com/")
        assertFalse(decision.allowed)
    }

    @Test
    fun loopbackAndPrivateIpv6AreLocal() {
        assertTrue(NetworkPolicy.isPrivateOrLocalHost("::1"))
        assertTrue(NetworkPolicy.isPrivateOrLocalHost("fd00::21"))
        assertTrue(NetworkPolicy.isPrivateOrLocalHost("fe80::1"))
    }

    @Test
    fun publicAddressIsNotLocal() {
        assertFalse(NetworkPolicy.isPrivateOrLocalHost("8.8.8.8"))
        assertFalse(NetworkPolicy.isPrivateOrLocalHost("example.com"))
    }
}
