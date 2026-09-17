from pathlib import Path

from vinylyrics.recognition.cache import DiskRecognitionCache, hash_audio


def test_hash_audio_is_deterministic_and_sensitive_to_content():
    a = b"hello world"
    b = b"hello world"
    c = b"different"
    assert hash_audio(a) == hash_audio(b)
    assert hash_audio(a) != hash_audio(c)


def test_cache_roundtrip(tmp_path: Path):
    cache = DiskRecognitionCache(tmp_path / "cache")
    audio_hash = hash_audio(b"fragment")
    assert cache.get(audio_hash) is None

    cache.set(audio_hash, {"track": {"title": "Foo"}})
    assert cache.get(audio_hash) == {"track": {"title": "Foo"}}


def test_cache_creates_directory_if_missing(tmp_path: Path):
    cache_dir = tmp_path / "nested" / "cache"
    assert not cache_dir.exists()
    DiskRecognitionCache(cache_dir)
    assert cache_dir.exists()
