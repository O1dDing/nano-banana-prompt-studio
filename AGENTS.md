# Project Instructions

## Python

Use `D:\\software_new\\anaconda3\\envs\\test\\python.exe` for Python commands and tests unless the task explicitly requires another environment.

## Architecture

- Domain code lives in `src/nano_banana/core/` (no Qt, no Flask).
- Prompt fields are defined only in `src/nano_banana/core/schema.yaml`.
- Image providers implement the protocol in `src/nano_banana/core/images/` and register in `_registry()`.
- See `ARCHITECTURE.md` and `CONTRIBUTING.md`.
