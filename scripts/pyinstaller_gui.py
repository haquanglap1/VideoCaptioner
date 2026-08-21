import os
import sys


def _open_windows_standard_stream(handle_id: int):
    """Wrap an inherited console or redirected pipe handle in a text stream."""
    descriptor_id = 1 if handle_id == -11 else 2
    try:
        descriptor = os.dup(descriptor_id)
        return open(
            descriptor,
            "w",
            encoding="utf-8",
            errors="replace",
            buffering=1,
            closefd=True,
        )
    except OSError:
        pass
    try:
        import ctypes
        import msvcrt

        kernel32 = ctypes.windll.kernel32
        kernel32.GetStdHandle.restype = ctypes.c_void_p
        source_handle = kernel32.GetStdHandle(handle_id)
        invalid_handle = ctypes.c_void_p(-1).value
        if not source_handle or source_handle == invalid_handle:
            return None
        duplicate_handle = ctypes.c_void_p()
        current_process = kernel32.GetCurrentProcess()
        duplicate_same_access = 0x00000002
        if not kernel32.DuplicateHandle(
            current_process,
            ctypes.c_void_p(source_handle),
            current_process,
            ctypes.byref(duplicate_handle),
            0,
            True,
            duplicate_same_access,
        ):
            return None
        descriptor = msvcrt.open_osfhandle(duplicate_handle.value, os.O_WRONLY)
        return open(
            descriptor,
            "w",
            encoding="utf-8",
            errors="replace",
            buffering=1,
            closefd=True,
        )
    except (AttributeError, OSError, ValueError):
        return None


def _prepare_cli_streams() -> None:
    """Reuse the caller's console without showing one for normal GUI startup."""
    if os.name == "nt" and (sys.stdout is None or sys.stderr is None):
        try:
            import ctypes

            attach_parent_process = 0xFFFFFFFF
            ctypes.windll.kernel32.AttachConsole(attach_parent_process)
        except (AttributeError, OSError):
            pass
        if sys.stdout is None:
            sys.stdout = _open_windows_standard_stream(-11)
        if sys.stderr is None:
            sys.stderr = _open_windows_standard_stream(-12)
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        _prepare_cli_streams()
        from videocaptioner.cli.main import main

        raise SystemExit(main(sys.argv[1:]))
    from videocaptioner.ui.main import main

    main()
