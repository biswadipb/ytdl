import ytdl


def report(name, done, total, status="downloading", formats=2, **extra):
    d = dict(filename=name, downloaded_bytes=done, total_bytes=total, status=status,
             info_dict={"requested_formats": [1] * formats})
    d.update(extra)
    return d


def test_video_then_audio_is_one_steadily_rising_number():
    p, seen = ytdl.Progress(), []
    for done in range(0, 101, 10):
        seen.append(p.update(report("v.mp4", done * 9, 900)))
    seen.append(p.update(report("v.mp4", 900, 900, status="finished")))
    for done in range(0, 101, 20):
        seen.append(p.update(report("a.m4a", done, 100)))
    assert seen == sorted(seen), "progress must never go backwards"
    assert seen[-1] <= 0.99 and seen[-1] > 0.95


def test_second_stream_does_not_reset_the_bar():
    p = ytdl.Progress()
    p.update(report("v.mp4", 900, 900, status="finished"))
    before = p.value
    assert p.update(report("a.m4a", 0, 100)) >= before


def test_changing_size_estimates_never_lower_it():
    p = ytdl.Progress()
    a = p.update(report("v.mp4", 500, 1000, formats=1))
    b = p.update(report("v.mp4", 600, 2500, formats=1))     # yt-dlp revised its guess upwards
    assert b >= a


def test_fragments_without_sizes_still_move():
    p = ytdl.Progress()
    d = dict(filename="f", status="downloading", fragment_index=5, fragment_count=10, info_dict={})
    assert 0.4 < p.update(d) < 0.6


def test_nothing_known_yet_is_zero():
    assert ytdl.Progress().update({"status": "downloading", "info_dict": {}}) == 0.0
