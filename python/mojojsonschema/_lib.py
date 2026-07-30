"""Build and load the Mojo validation kernel."""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCE = os.path.join(ROOT, "src", "capi.mojo")
LIBRARY = os.environ.get("MOJOJSONSCHEMA_LIB") or os.path.join(
    ROOT, "dist", "libmojo-jsonschema.so"
)

I = ctypes.c_int64
_library: ctypes.CDLL | None = None
_runtime_device: int | bool | None = None
PARALLEL_THRESHOLD = 262144


class BuildError(RuntimeError):
    pass


def build(force: bool = False) -> str:
    if (
        not force
        and os.path.exists(LIBRARY)
        and (
            not os.path.exists(SOURCE)
            or os.path.getmtime(LIBRARY) >= os.path.getmtime(SOURCE)
        )
    ):
        return LIBRARY
    if os.environ.get("MOJOJSONSCHEMA_LIB"):
        raise BuildError(f"MOJOJSONSCHEMA_LIB does not exist or is stale: {LIBRARY}")
    if not os.path.exists(SOURCE):
        raise BuildError(
            f"no Mojo source at {SOURCE}; set MOJOJSONSCHEMA_LIB to a built library"
        )
    pixi = shutil.which("pixi")
    command = ["bash", os.path.join(ROOT, "build", "build.sh")]
    if shutil.which("mojo") is None and pixi:
        command = [
            pixi,
            "run",
            "--manifest-path",
            os.path.join(ROOT, "pixi.toml"),
            "build",
        ]
    process = subprocess.run(command, capture_output=True, text=True, timeout=1800)
    if process.returncode or not os.path.exists(LIBRARY):
        raise BuildError((process.stderr or process.stdout).strip()[:4000])
    return LIBRARY


def lib() -> ctypes.CDLL:
    global _library
    if _library is None:
        _library = ctypes.CDLL(build())
        fn = _library.mjs_validate_flat
        fn.argtypes = [I] * 14
        fn.restype = I
    return _library


def enable_parallel_runtime() -> bool:
    global _runtime_device
    if _runtime_device is None:
        try:
            initialize = lib().KGEN_CompilerRT_AsyncRT_GetOrCreateCPUDevice
            initialize.argtypes = []
            initialize.restype = ctypes.c_void_p
            _runtime_device = initialize() or False
        except (AttributeError, OSError):
            _runtime_device = False
    return _runtime_device is not False
