"""Deprecated alias. Prefer python -m ats_matcher.server or ats-match serve."""
from ats_matcher.server import (
    ASSETS,
    MAX_UPLOAD,
    MODES,
    create_engine,
    create_server,
    discover_gguf,
    gpu_layers_for_mode,
    launch,
    main,
    resolve_model,
)

__all__ = [
    "ASSETS",
    "MAX_UPLOAD",
    "MODES",
    "create_engine",
    "create_server",
    "discover_gguf",
    "gpu_layers_for_mode",
    "launch",
    "main",
    "resolve_model",
]


if __name__ == "__main__":
    main()
