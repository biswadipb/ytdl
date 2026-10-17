package dev.ytdl.minimal

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class RulesTest {
    private fun flags(audio: Boolean, choice: String) = downloadOptions(audio, choice, "/out", "name").toMap()

    @Test fun bestVideoMergesToMp4WithNoHeightLimit() {
        val o = flags(false, "best")
        assertEquals("bv*+ba/b", o["-f"])
        assertEquals("mp4", o["--merge-output-format"])
        assertEquals("mp4", o["--remux-video"])
        assertEquals("/out/name.%(ext)s", o["-o"])
    }

    @Test fun qualityCapsTheHeight() {
        assertEquals("bv*[height<=720]+ba/b[height<=720]", flags(false, "720")["-f"])
        assertEquals("bv*[height<=1080]+ba/b[height<=1080]", flags(false, "1080")["-f"])
    }

    @Test fun audioExtractsToTheChosenFormatAndOnlyMp3GetsCoverArt() {
        val mp3 = flags(true, "mp3")
        assertEquals("mp3", mp3["--audio-format"]); assertTrue("-x" in mp3); assertTrue("--embed-thumbnail" in mp3)
        val m4a = flags(true, "m4a")
        assertEquals("m4a", m4a["--audio-format"]); assertFalse("--embed-thumbnail" in m4a)
    }

    @Test fun neverDownloadsAWholePlaylistAndAlwaysTagsFiles() {
        listOf(false, true).forEach { audio ->
            val o = flags(audio, if (audio) "mp3" else "best")
            assertTrue("--no-playlist" in o); assertTrue("--embed-metadata" in o)
        }
    }

    @Test fun audioFilesGetASuffixSoTheyNeverReplaceAVideo() {
        assertEquals("%(title).150B [%(id)s]", fileName(false))
        assertEquals("%(title).150B [%(id)s] (audio)", fileName(true))
        assertEquals("zuck - Post [abc] (audio)", fileName(true, "zuck - Post [abc]"))
    }

    @Test fun findsLinksInCopiedOrSharedText() {
        assertEquals("https://youtu.be/jNQXAC9IVRw", firstLink("Me at the zoo https://youtu.be/jNQXAC9IVRw"))
        assertEquals("https://www.threads.com/@zuck/post/DSVRshjkbtK", firstLink("see (https://www.threads.com/@zuck/post/DSVRshjkbtK)."))
        assertEquals("https://vimeo.com/76979871", firstLink("https://vimeo.com/76979871"))
        assertNull(firstLink("hello")); assertNull(firstLink("https://example.com/x")); assertNull(firstLink(null))
    }

    @Test fun channelsAndPlaylistsAreRefused() {
        listOf("https://www.youtube.com/@TED", "https://www.youtube.com/channel/UC123", "https://www.youtube.com/playlist?list=PL1",
            "https://soundcloud.com/forss/sets/album", "https://www.instagram.com/nasa/").forEach { assertTrue(it, isChannelOrPlaylist(it)) }
        listOf("https://www.youtube.com/watch?v=jNQXAC9IVRw", "https://youtu.be/abc", "https://www.instagram.com/reel/Cabc/",
            "https://x.com/NASA/status/1").forEach { assertFalse(it, isChannelOrPlaylist(it)) }
    }

    @Test fun onlyTemporaryErrorsAreRetried() {
        assertTrue(isTransient("Unable to download webpage: connection reset"))
        assertFalse(isTransient("Video unavailable")); assertFalse(isTransient("Sign in to confirm your age"))
    }

    @Test fun errorsAreShortenedToOneReadableLine() {
        assertEquals("Video unavailable", friendlyError("WARNING: x\nERROR: [youtube] abc: Video unavailable\nmore"))
        assertTrue(friendlyError(null).isNotEmpty())
        assertTrue(friendlyError("ERROR: " + "x".repeat(500)).length <= 90)
    }

    @Test fun threadsAnswersAreParsed() {
        assertTrue(isThreadsUrl("https://www.threads.com/@zuck/post/DSVRshjkbtK"))
        val scrape = parseThreadsScrape("{\"videos\":[\"https://v/1.mp4\"],\"title\":\"T\",\"image\":\"\"}")!!
        assertEquals(listOf("https://v/1.mp4"), scrape.videos); assertNull(scrape.image)
    }

    @Test fun themeChoicesMatchTheirLabelsAndJunkMeansAuto() {
        assertEquals(listOf("auto", "light", "dark"), THEMES)
        assertEquals(listOf("Auto", "Light", "Dark"), THEME_LABELS)
        assertEquals("dark", cleanTheme("dark")); assertEquals("auto", cleanTheme("sepia")); assertEquals("auto", cleanTheme(null))
    }
}
