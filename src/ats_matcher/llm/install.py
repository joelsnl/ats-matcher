from __future__ import annotations

import subprocess
import sys

WHEEL_INDEXES = {
    "vulkan": "https://abetlen.github.io/llama-cpp-python/whl/vulkan",
    "cpu": "https://abetlen.github.io/llama-cpp-python/whl/cpu",
    "cuda": "https://abetlen.github.io/llama-cpp-python/whl/cu124",
}

DEFAULT_VERSION = "0.3.35"


def install_llama_cpp(backend: str = "cpu", version: str = DEFAULT_VERSION) -> None:
    """Install a prebuilt llama-cpp-python wheel (no C++ compiler required)."""
    if backend not in WHEEL_INDEXES:
        raise ValueError(f"Unknown backend {backend!r}. Choose: {', '.join(WHEEL_INDEXES)}")
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--only-binary=:all:",
        "--extra-index-url",
        WHEEL_INDEXES[backend],
        f"llama-cpp-python=={version}",
    ]
    subprocess.check_call(cmd)
