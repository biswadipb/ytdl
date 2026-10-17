package dev.ytdl.app

import org.junit.Assert.assertEquals
import org.junit.Test

class SaveFolderTest {
    @Test fun readsFoldersTheWayAPersonWould() {
        assertEquals("Downloads/ytdl", prettyFolder(""))
        assertEquals("Movies/ytdl", prettyFolder("content://com.android.externalstorage.documents/tree/primary%3AMovies%2Fytdl"))
        assertEquals("Internal storage", prettyFolder("content://com.android.externalstorage.documents/tree/primary%3A"))
        assertEquals("SD card/Videos/clips", prettyFolder("content://com.android.externalstorage.documents/tree/1234-ABCD%3AVideos%2Fclips"))
        assertEquals("SD card", prettyFolder("content://com.android.externalstorage.documents/tree/1234-ABCD%3A"))
        assertEquals("Downloads", prettyFolder("content://com.android.providers.downloads.documents/tree/downloads"))
    }
}
