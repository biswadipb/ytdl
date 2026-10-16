package dev.ytdl.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ShareAndStorageTest {
    @Test fun findsTheLinkInsideSharedText() {
        assertEquals("https://youtu.be/jNQXAC9IVRw", firstLink("Me at the zoo https://youtu.be/jNQXAC9IVRw"))
        assertEquals("https://www.instagram.com/reel/Cabc123/", firstLink("look (https://www.instagram.com/reel/Cabc123/)."))
        assertNull(firstLink("no link here"))
        assertNull(firstLink("https://example.com/video"))
        assertNull(firstLink(null))
    }

    @Test fun singleVideosMayAutoStart() {
        listOf(
            "https://www.youtube.com/watch?v=jNQXAC9IVRw", "https://youtu.be/jNQXAC9IVRw", "https://www.youtube.com/shorts/abc123",
            "https://www.instagram.com/reel/Cabc123/", "https://www.instagram.com/p/Cabc123/",
            "https://x.com/NASA/status/1234567890", "https://twitter.com/NASA/status/1234567890",
            "https://www.facebook.com/watch/?v=123", "https://fb.watch/abc/", "https://www.threads.com/@zuck/post/DSVRshjkbtK",
            "https://www.dailymotion.com/video/x7or79x", "https://dai.ly/x7or79x",
            "https://www.tiktok.com/@scout2015/video/6718335390845095173", "https://vm.tiktok.com/ZMabc/",
            "https://www.reddit.com/r/videos/comments/6rrwyj/title/", "https://redd.it/6rrwyj",
            "https://vimeo.com/76979871", "https://clips.twitch.tv/FaintLightGull", "https://www.twitch.tv/videos/1234567",
            "https://soundcloud.com/forss/flickermood", "https://on.soundcloud.com/abcdEF",
        ).forEach { assertTrue(it, isSingleItemLink(it)) }
    }

    @Test fun channelsProfilesAndPlaylistsNeverAutoStart() {
        listOf(
            "https://www.youtube.com/@TED", "https://www.youtube.com/channel/UC123", "https://www.youtube.com/playlist?list=PL1",
            "https://www.youtube.com/@TED/videos", "https://www.instagram.com/nasa/", "https://x.com/NASA",
            "https://www.tiktok.com/@scout2015", "https://soundcloud.com/forss", "https://soundcloud.com/forss/sets/album",
            "https://www.reddit.com/r/videos/", "https://vimeo.com/channels/staffpicks", "https://www.twitch.tv/somestreamer",
            "https://www.dailymotion.com/someuser", "https://www.threads.com/@zuck",
        ).forEach { assertFalse(it, isSingleItemLink(it)) }
    }

    private fun file(name: String, gb: Double, ageDays: Int, now: Long) =
        StoredFile(name, (gb * 1000).toLong(), now - ageDays * 86_400_000L)

    @Test fun cleanupDeletesOldFilesThenTrimsOldestToTheCap() {
        val now = 1_000_000_000_000L
        val files = listOf(file("old", 1.0, 40, now), file("mid", 1.0, 10, now), file("new", 1.0, 1, now))
        assertEquals(listOf("old"), planCleanup(files, 30, 0, now, gb = 1000).map { it.ref })
        assertEquals(listOf("old"), planCleanup(files, 0, 2, now, gb = 1000).map { it.ref })       // cap trims the oldest
        assertEquals(listOf("old", "mid"), planCleanup(files, 0, 1, now, gb = 1000).map { it.ref })
        assertTrue(planCleanup(files, 0, 0, now, gb = 1000).isEmpty())                              // limits off
        assertEquals(listOf("old", "mid"), planCleanup(files, 30, 1, now, gb = 1000).map { it.ref }) // both rules together
    }

    @Test fun sizesAreReadable() {
        assertEquals("500 B", humanSize(500))
        assertEquals("1.5 KB", humanSize(1536))
        assertEquals("2.0 GB", humanSize(2L * 1024 * 1024 * 1024))
    }
}
