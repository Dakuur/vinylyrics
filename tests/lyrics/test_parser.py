from vinylyrics.lyrics.base import LyricsResult
from vinylyrics.lyrics.parser import LyricLine, parse_lrc


def test_parse_lrc_skips_metadata_tags():
    text = "[ar:Jarabe de Palo]\n[ti:Bonito]\n[00:12.34]Primera linea\n"
    lines = parse_lrc(text)
    assert lines == [LyricLine(ms=12340, text="Primera linea")]


def test_parse_lrc_expands_multiple_timestamps_on_one_line():
    text = "[00:20.00][00:45.50]Estribillo repetido\n"
    lines = parse_lrc(text)
    assert lines == [
        LyricLine(ms=20000, text="Estribillo repetido"),
        LyricLine(ms=45500, text="Estribillo repetido"),
    ]


def test_parse_lrc_keeps_empty_interlude_lines():
    text = "[00:30.00]\n[00:35.00]Texto\n"
    lines = parse_lrc(text)
    assert lines == [
        LyricLine(ms=30000, text=""),
        LyricLine(ms=35000, text="Texto"),
    ]


def test_parse_lrc_handles_two_and_three_digit_fractions():
    text = "[00:12.34]Dos digitos\n[00:35.123]Tres digitos\n"
    lines = parse_lrc(text)
    assert lines[0].ms == 12340
    assert lines[1].ms == 35123


def test_parse_lrc_sorts_by_timestamp_regardless_of_source_order():
    text = "[00:45.50]Estribillo\n[00:20.00]Primera\n"
    lines = parse_lrc(text)
    assert [l.ms for l in lines] == [20000, 45500]


def test_parse_lrc_against_real_lrclib_content():
    # A real synced-lyrics excerpt fetched from LRCLIB for "Bonito" by
    # Jarabe de Palo during planning, trimmed to the first few lines plus
    # the real trailing empty interlude line.
    text = (
        "[00:10.97] Bonito, todo me parece bonito\n"
        "[00:18.97] Bonita mañana, bonito lugar\n"
        "[00:23.15] Bonita la cama, que bien se ve el mar\n"
        "[03:38.97] \n"
    )
    lines = parse_lrc(text)
    assert lines[0] == LyricLine(ms=10970, text="Bonito, todo me parece bonito")
    assert lines[1] == LyricLine(ms=18970, text="Bonita mañana, bonito lugar")
    assert lines[2] == LyricLine(ms=23150, text="Bonita la cama, que bien se ve el mar")
    assert lines[3] == LyricLine(ms=218970, text="")


def test_lyrics_result_has_synced_reflects_line_count():
    with_lines = LyricsResult(synced_lines=(LyricLine(ms=0, text="hi"),), plain_lyrics=None, instrumental=False)
    without_lines = LyricsResult(synced_lines=(), plain_lyrics="plain text only", instrumental=False)
    assert with_lines.has_synced is True
    assert without_lines.has_synced is False
