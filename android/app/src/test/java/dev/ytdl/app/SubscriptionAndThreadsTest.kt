package dev.ytdl.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SubscriptionAndThreadsTest {
    private fun entry(id: String, upcoming: Boolean = false) = Entry(id, "https://v/$id", id, upcoming)

    @Test fun channelLinksPointAtTheirVideosTab() {
        assertEquals("https://www.youtube.com/@TED/videos", listingUrl("https://www.youtube.com/@TED"))
        assertEquals("https://www.youtube.com/@TED/videos", listingUrl("https://www.youtube.com/@TED/"))
        assertEquals("https://www.youtube.com/channel/UC1/videos", listingUrl("https://www.youtube.com/channel/UC1"))
        assertEquals("https://www.youtube.com/@TED/shorts", listingUrl("https://www.youtube.com/@TED/shorts"))
        assertEquals("https://www.youtube.com/playlist?list=PL1", listingUrl("https://www.youtube.com/playlist?list=PL1"))
        assertEquals("https://example.com/feed", listingUrl(" https://example.com/feed "))
    }

    @Test fun newUploadsComeOldestFirstAndSkipSeenAndScheduledLivestreams() {
        val listing = listOf(entry("live", upcoming = true), entry("c"), entry("b"), entry("a"), entry("old"))
        assertEquals(listOf("a", "b", "c"), newEntries(setOf("old"), listing).map { it.id })
        assertTrue(newEntries(setOf("a", "b", "c", "old", "live"), listing).isEmpty())
    }

    @Test fun seenListKeepsNewestFirstAndIsCapped() {
        assertEquals(listOf("n1", "n2", "x"), mergeSeen(listOf("x"), listOf("n1", "n2")))
        assertEquals(listOf("n1", "n2", "x"), mergeSeen(listOf("x", "n1"), listOf("n1", "n2")))  // no duplicates
        val many = (1..600).map { "id$it" }
        assertEquals(SEEN_LIMIT, mergeSeen(many, listOf("fresh")).size)
        assertEquals("fresh", mergeSeen(many, listOf("fresh")).first())
    }

    @Test fun dueOnlyAfterTheInterval() {
        val hour = 3_600_000L
        assertTrue(isDue(0, 10 * hour, 6))
        assertFalse(isDue(5 * hour, 10 * hour, 6))
        assertTrue(isDue(4 * hour, 10 * hour, 6))
    }

    @Test fun nightIsElevenPmToSevenAm() {
        listOf(23, 0, 3, 6).forEach { assertTrue("hour $it", isNight(it)) }
        listOf(7, 12, 18, 22).forEach { assertFalse("hour $it", isNight(it)) }
    }

    @Test fun recognisesThreadsPostLinks() {
        assertTrue(isThreadsUrl("https://www.threads.com/@zuck/post/DSVRshjkbtK"))
        assertTrue(isThreadsUrl("https://www.threads.net/@zuck/post/abc-123"))
        assertTrue(isThreadsUrl("https://www.threads.com/t/abc123"))
        assertFalse(isThreadsUrl("https://www.threads.com/@zuck"))
        assertFalse(isThreadsUrl("https://example.com/@zuck/post/abc"))
        assertEquals("zuck" to "DSVRshjkbtK", threadsParts("https://www.threads.com/@zuck/post/DSVRshjkbtK"))
        assertNull(threadsParts("https://www.threads.com/t/abc123"))
    }

    @Test fun readsThePageScriptAnswer() {
        val inner = """{"videos":["https://v.test/1.mp4","https://v.test/2.mp4"],"title":"My caption","image":"https://img.test/x.jpg"}"""
        // evaluateJavascript hands back the string with an extra layer of JSON quoting
        val quoted = "\"" + inner.replace("\"", "\\\"") + "\""
        val scrape = parseThreadsScrape(quoted)!!
        assertEquals(listOf("https://v.test/1.mp4", "https://v.test/2.mp4"), scrape.videos)
        assertEquals("My caption", scrape.title)
        assertEquals("https://img.test/x.jpg", scrape.image)
        assertTrue(parseThreadsScrape(inner)!!.videos.size == 2)          // unquoted works too
        assertNull(parseThreadsScrape("null"))
        assertNull(parseThreadsScrape(null))
        assertTrue(parseThreadsScrape("""{"videos":[],"title":"","image":""}""")!!.videos.isEmpty())
    }

    @Test fun threadsFilesFollowTheNamingAndFolderRules() {
        val post = ThreadsPost("zuck", "DSVRshjkbtK", "Open sourcing: a/b 100%", null, listOf("u1", "u2"))
        assertEquals("Open sourcing a b 100 (1-of-2) [DSVRshjkbtK-1]" to "", threadsNaming(post, 0, 2, "title-id", "flat"))
        assertEquals("zuck - Open sourcing a b 100 (2-of-2)" to "Threads/zuck/", threadsNaming(post, 1, 2, "channel-title", "site-channel"))
        assertEquals("Open sourcing a b 100 [DSVRshjkbtK]" to "zuck/", threadsNaming(post, 0, 1, "title-id", "channel"))
        val untitled = ThreadsPost("zuck", "CODE1", "", null, listOf("u"))
        assertEquals("Threads post CODE1 [CODE1]", threadsNaming(untitled, 0, 1, "title-id", "flat").first)
    }

    @Test fun fileTextNeverContainsTemplateOrPathCharacters() {
        val text = safeFileText("50% off / now: \"sale\"?\nline2")
        assertFalse(text.any { it in "%/\\:*?\"<>|\n" })
    }

    @Test fun linkPatternRecognisesTheNewSites() {
        assertTrue(LINK_PATTERN.containsMatchIn("see https://www.dailymotion.com/video/x7or79x ok"))
        assertTrue(LINK_PATTERN.containsMatchIn("https://dai.ly/x7or79x"))
        assertTrue(LINK_PATTERN.containsMatchIn("https://www.threads.com/@zuck/post/DSVRshjkbtK"))
    }
}
