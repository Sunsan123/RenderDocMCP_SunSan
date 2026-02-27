from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

SERVER_NAME = "renderdoc-mcp"
DEFAULT_RENDERDOC_PATH = os.getenv("RENDERDOC_PATH", "qrenderdoc")
DEFAULT_CAPTURE_DIR = Path(os.getenv("RENDERDOC_CAPTURE_DIR", "./captures")).resolve()

mcp = FastMCP(SERVER_NAME)


def _run_command(args: list[str]) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "command": " ".join(args),
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "returncode": 127,
            "stdout": "",
            "stderr": f"RenderDoc binary not found: {args[0]}",
            "command": " ".join(args),
        }


@mcp.tool()
def health_check() -> str:
    """Check whether RenderDoc CLI is available."""
    result = _run_command([DEFAULT_RENDERDOC_PATH, "--help"])
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def create_capture_dir(path: str | None = None) -> str:
    """Create capture directory and return absolute path."""
    target = Path(path).expanduser().resolve() if path else DEFAULT_CAPTURE_DIR
    target.mkdir(parents=True, exist_ok=True)
    return str(target)


@mcp.tool()
def list_captures(path: str | None = None) -> str:
    """List RenderDoc capture files (.rdc) in the capture directory."""
    target = Path(path).expanduser().resolve() if path else DEFAULT_CAPTURE_DIR
    if not target.exists():
        return json.dumps({"ok": False, "error": f"Path not found: {target}"}, ensure_ascii=False)

    captures = sorted(str(p) for p in target.glob("*.rdc"))
    return json.dumps({"ok": True, "path": str(target), "captures": captures}, ensure_ascii=False, indent=2)


@mcp.tool()
def launch_renderdoc(capture_file: str | None = None, renderdoc_path: str | None = None) -> str:
    """Launch RenderDoc GUI (qrenderdoc), optionally opening a specific .rdc file."""
    binary = renderdoc_path or DEFAULT_RENDERDOC_PATH
    args = [binary]

    if capture_file:
        cap = Path(capture_file).expanduser().resolve()
        if not cap.exists():
            return json.dumps({"ok": False, "error": f"Capture file not found: {cap}"}, ensure_ascii=False)
        args.append(str(cap))

    result = _run_command(args)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def open_capture(capture_file: str, renderdoc_path: str | None = None) -> str:
    """Open an existing .rdc capture file in RenderDoc GUI."""
    return launch_renderdoc(capture_file=capture_file, renderdoc_path=renderdoc_path)


@mcp.tool()
def export_capture_index(path: str | None = None, output_file: str = "capture_index.json") -> str:
    """Export current capture file list to JSON for indexing."""
    target = Path(path).expanduser().resolve() if path else DEFAULT_CAPTURE_DIR
    captures = sorted(str(p) for p in target.glob("*.rdc")) if target.exists() else []

    output = Path(output_file).expanduser().resolve()
    payload = {
        "path": str(target),
        "count": len(captures),
        "captures": captures,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(output)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
