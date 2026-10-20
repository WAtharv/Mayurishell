"""Unit tests for website and folder launch services."""
from pathlib import Path
from unittest.mock import patch

from services.launcher_service import (
    launch_folder,
    launch_website,
    validate_web_url,
)


def test_validate_web_url_valid() -> None:
    """Test valid http and https URLs."""
    valid, norm = validate_web_url("https://www.google.com")
    assert valid is True
    assert norm == "https://www.google.com"

    valid, norm = validate_web_url("http://example.com/page?q=1")
    assert valid is True
    assert norm == "http://example.com/page?q=1"


def test_validate_web_url_autoprefix_https() -> None:
    """Test URLs without scheme get https:// prefix."""
    valid, norm = validate_web_url("github.com/WAtharv")
    assert valid is True
    assert norm == "https://github.com/WAtharv"


def test_validate_web_url_invalid_schemes() -> None:
    """Test only http and https are permitted."""
    valid, err = validate_web_url("ftp://files.example.com")
    assert valid is False
    assert "Only 'http' and 'https' are allowed" in err

    valid, err = validate_web_url("javascript:alert(1)")
    assert valid is False

    valid, err = validate_web_url("")
    assert valid is False


def test_launch_website() -> None:
    """Test launching a website via webbrowser."""
    with patch("webbrowser.open", return_value=True) as mock_open:
        success, msg = launch_website("youtube.com")
        assert success is True
        mock_open.assert_called_once_with("https://youtube.com")


def test_launch_website_invalid_url() -> None:
    """Test launching an invalid URL fails without calling browser."""
    with patch("webbrowser.open") as mock_open:
        success, msg = launch_website("ftp://invalid.com")
        assert success is False
        mock_open.assert_not_called()


def test_launch_folder_existing(tmp_path: Path) -> None:
    """Test launching an existing folder."""
    folder = tmp_path / "my_projects"
    folder.mkdir()

    with patch("os.startfile", create=True) as mock_startfile:
        success, msg, path = launch_folder(str(folder))
        assert success is True
        assert path == folder.resolve()
        mock_startfile.assert_called_once_with(str(folder.resolve()))


def test_launch_folder_missing(tmp_path: Path) -> None:
    """Test launching a non-existent folder returns error."""
    missing = tmp_path / "nonexistent_dir"
    success, msg, path = launch_folder(str(missing))
    assert success is False
    assert "Folder does not exist" in msg


def test_launch_folder_is_file(tmp_path: Path) -> None:
    """Test launch_folder fails if path points to a file, not a directory."""
    sample_file = tmp_path / "notes.txt"
    sample_file.write_text("hello")

    success, msg, path = launch_folder(str(sample_file))
    assert success is False
    assert "Path is a file, not a directory" in msg
