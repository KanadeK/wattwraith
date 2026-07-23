from wattwraith import __version__


def test_prerelease_version_is_explicit() -> None:
    assert __version__ == "0.1.0.dev0"
