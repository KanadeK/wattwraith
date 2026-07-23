from wattwraith import __version__


def test_release_version_is_explicit() -> None:
    assert __version__ == "0.1.0"
