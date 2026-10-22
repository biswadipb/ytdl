package dev.ytdl.app

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RedditImagesTest {
    @Test fun links() {
        assertTrue(isRedditUrl("https://www.reddit.com/r/pics/comments/abc123/a_view/"))
        assertTrue(isRedditUrl("https://redd.it/abc123"))
        assertTrue(isRedditUrl("https://www.reddit.com/r/pics/s/AbCdEf"))
        assertFalse(isRedditUrl("https://www.reddit.com/r/pics/"))
        assertEquals("abc123", redditPostId("https://old.reddit.com/r/pics/comments/abc123/x"))
    }

    @Test fun galleryGivesOriginalsInOrderAndSkipsBrokenOnes() {
        val post = JSONObject("""{"is_gallery":true,
          "gallery_data":{"items":[{"media_id":"m1"},{"media_id":"m2"},{"media_id":"m3"}]},
          "media_metadata":{
            "m1":{"status":"valid","e":"Image","m":"image/jpg","s":{"u":"https://preview.redd.it/m1.jpg?a=1&amp;b=2"}},
            "m2":{"status":"valid","e":"Image","m":"image/png"},
            "m3":{"status":"failed","e":"Image","m":"image/jpg"}}}""")
        val pics = redditPictures(post)
        assertEquals(listOf("jpg", "png"), pics.map { it.ext })
        assertEquals(listOf("https://i.redd.it/m1.jpg", "https://preview.redd.it/m1.jpg?a=1&b=2"), pics[0].choices)
    }

    @Test fun singleImageButNotOtherSitesOrVideos() {
        assertEquals("jpg", redditPictures(JSONObject("""{"url_overridden_by_dest":"https://i.redd.it/x.JPEG"}""")).single().ext)
        assertTrue(redditPictures(JSONObject("""{"url":"https://example.com/pic.jpg"}""")).isEmpty())
        assertTrue(redditPictures(JSONObject("""{"is_video":true,"url":"https://i.redd.it/x.gif"}""")).isEmpty())
        assertTrue(redditPictures(JSONObject("""{"post_hint":"hosted:video","url":"https://v.redd.it/z"}""")).isEmpty())
    }

    @Test fun crosspostsUseTheOriginal() {
        val p = JSONObject("""{"crosspost_parent_list":[{"url":"https://i.redd.it/o.png"}]}""")
        assertEquals("png", redditPictures(p).single().ext)
    }

    @Test fun fileNamesAreSafe() {
        assertEquals("Trip day 1 [p1] (1 of 2).jpg", redditFileName("Trip: day 1", "p1", 0, 2, "jpg"))
        assertEquals("reddit [p1].png", redditFileName("  ...  ", "p1", 0, 1, "png"))
    }
}
