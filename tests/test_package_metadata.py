import src


def test_package_version_is_defined() -> None:
    assert isinstance(src.__version__, str)
    assert src.__version__

