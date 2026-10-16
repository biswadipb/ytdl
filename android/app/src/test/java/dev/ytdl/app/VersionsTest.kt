package dev.ytdl.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class VersionsTest {
    @Test fun parsesVersions() {
        assertEquals(listOf(2, 1, 0), parseVersion("v2.1.0"))
        assertEquals(listOf(3, 0, 0), parseVersion("3"))
        assertNull(parseVersion("dev"))
        assertNull(parseVersion(null))
    }

    @Test fun comparesVersions() {
        assertTrue(isNewer("2.0.0", "v2.1.0"))
        assertTrue(isNewer("2.9.9", "3.0.0"))
        assertFalse(isNewer("2.1.0", "v2.1.0"))
        assertFalse(isNewer("2.1.1", "2.1.0"))
        assertFalse(isNewer("dev", "9.9.9"))
        assertFalse(isNewer("1.0.0", "not-a-version"))
    }

    @Test fun parsesClipTimes() {
        assertEquals(90.0, parseClock("1:30")!!, 0.0)
        assertEquals(3723.0, parseClock("1:02:03")!!, 0.0)
        assertEquals(45.5, parseClock("45.5")!!, 0.0)
        assertNull(parseClock("  "))
        assertThrows { parseClock("a:b") }
        assertThrows { parseClock("1:2:3:4") }
    }

    @Test fun decidesWhichErrorsAreWorthRetrying() {
        assertTrue(isTransientError("HTTP Error 503: Service Unavailable".replace("Unavailable", "busy")))
        assertTrue(isTransientError("Unable to download webpage: connection reset"))
        assertFalse(isTransientError("Video unavailable"))
        assertFalse(isTransientError("Unsupported URL: https://example.com"))
        assertFalse(isTransientError("Sign in to confirm your age"))
    }

    private fun assertThrows(block: () -> Unit) {
        try { block() } catch (e: NumberFormatException) { return }
        throw AssertionError("expected NumberFormatException")
    }
}
