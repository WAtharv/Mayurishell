import ast
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.application_discovery import (
    DETACHED_FLAGS,
    find_executable,
    is_startfile_target,
    is_uri,
    launch_application,
    launch_detached,
)


def test_is_uri_and_startfile_targets() -> None:
    """Test URI protocol, store app, and virtual shell folder detection."""
    assert is_uri("spotify:") is True
    assert is_uri("discord:") is True
    assert is_uri("whatsapp:") is True
    assert is_uri("ms-windows-store:") is True
    assert is_uri("https://google.com") is True
    # Microsoft Store AppsFolder target
    assert is_startfile_target(r"shell:AppsFolder\5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App") is True
    assert is_uri(r"shell:AppsFolder\CustomApp!App") is True

    # Not URIs / not startfile targets
    assert is_uri("notepad.exe") is False
    assert is_uri("code") is False
    assert is_uri(r"C:\Windows\System32\notepad.exe") is False


def test_find_executable_via_which() -> None:
    """Test finding executable via PATH (shutil.which)."""
    with patch("shutil.which", return_value="C:\\Fake\\notepad.exe"):
        found = find_executable("notepad")
        assert found == "C:\\Fake\\notepad.exe"


def test_find_executable_direct_file(tmp_path: Path) -> None:
    """Test finding executable when an explicit file path is provided."""
    dummy_exe = tmp_path / "myapp.exe"
    dummy_exe.write_text("dummy binary content")

    found = find_executable(str(dummy_exe))
    assert found == str(dummy_exe)


def test_find_executable_not_found() -> None:
    """Test find_executable returns None when app cannot be resolved."""
    with patch("shutil.which", return_value=None):
        found = find_executable("completely_nonexistent_app_12345")
        assert found is None


def test_launch_detached_uri_and_store_app() -> None:
    """Test launching URI protocol targets and Microsoft Store apps with explorer.exe and DEVNULL streams."""
    with patch("subprocess.Popen") as mock_popen:
        assert launch_detached("spotify:") is True
        mock_popen.assert_called_with(
            ["explorer.exe", "spotify:"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )

        assert launch_detached("whatsapp:") is True
        mock_popen.assert_called_with(
            ["explorer.exe", "whatsapp:"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )

        store_target = r"shell:AppsFolder\5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"
        assert launch_detached(store_target) is True
        mock_popen.assert_called_with(
            ["explorer.exe", store_target],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )


def test_launch_detached_executable_streams_and_flags() -> None:
    """Assert launch_detached uses CREATE_NEW_CONSOLE, DEVNULL, close_fds, and shell=False without SW_HIDE."""
    with patch("services.application_discovery.find_executable", return_value="C:\\Fake\\code.exe"):
        with patch("subprocess.Popen") as mock_popen:
            success = launch_detached("code", ["my_project"])
            assert success is True
            mock_popen.assert_called_once()
            args, kwargs = mock_popen.call_args

            # Argument list check
            assert args[0] == ["C:\\Fake\\code.exe", "my_project"]
            assert kwargs.get("shell") is False
            assert kwargs.get("close_fds") is True

            # All three streams must be subprocess.DEVNULL
            assert kwargs.get("stdin") == subprocess.DEVNULL
            assert kwargs.get("stdout") == subprocess.DEVNULL
            assert kwargs.get("stderr") == subprocess.DEVNULL

            # CREATE_NEW_CONSOLE flag (0x00000010)
            flags = kwargs.get("creationflags", 0)
            assert flags & 0x00000010

            # Window visibility: must not hide GUI window with SW_HIDE
            startupinfo = kwargs.get("startupinfo")
            if startupinfo is not None:
                assert not (startupinfo.dwFlags & subprocess.STARTF_USESHOWWINDOW and startupinfo.wShowWindow == subprocess.SW_HIDE)


def test_launch_detached_executable_fallback_to_explorer() -> None:
    """Test falling back to explorer.exe if direct execution raises an error."""
    with patch("services.application_discovery.find_executable", return_value="C:\\Fake\\guiapp.exe"):
        with patch("subprocess.Popen", side_effect=[OSError("Direct execution blocked"), MagicMock()]) as mock_popen:
            success = launch_detached("guiapp")
            assert success is True
            assert mock_popen.call_count == 2
            # Second call was fallback through explorer.exe
            second_call_args, second_call_kwargs = mock_popen.call_args_list[1]
            assert second_call_args[0] == ["explorer.exe", "C:\\Fake\\guiapp.exe"]
            assert second_call_kwargs.get("stdin") == subprocess.DEVNULL
            assert second_call_kwargs.get("shell") is False


def test_launch_detached_not_found() -> None:
    """Test launch_detached returns False when executable is not found."""
    with patch("services.application_discovery.find_executable", return_value=None):
        success = launch_detached("missing_app")
        assert success is False


def test_no_other_module_calls_popen_for_app_launching() -> None:
    """Ensure no module in commands/ directly calls subprocess.Popen or os.startfile for launching apps."""
    commands_dir = Path(__file__).parent.parent / "commands"
    assert commands_dir.is_dir()

    for py_file in commands_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # Check imports
            if isinstance(node, ast.ImportFrom):
                if node.module == "subprocess":
                    for name in node.names:
                        assert name.name != "Popen", f"Forbidden Popen import in {py_file.name}"
            # Check attribute access e.g. subprocess.Popen
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "Popen":
                    assert False, f"Forbidden direct subprocess.Popen call found in {py_file.name}"

