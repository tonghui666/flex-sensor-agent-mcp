"""Stdio-to-HTTP proxy for running COMSOL outside the MCP stdio process."""

from __future__ import annotations

import anyio
import asyncio
import base64
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

from mcp import ClientSession, types
from mcp.client.streamable_http import streamablehttp_client
from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server


T = TypeVar("T")

ROOT = Path(__file__).resolve().parent.parent
HOST = os.environ.get("COMSOL_MCP_HTTP_HOST", "127.0.0.1")
PORT = int(os.environ.get("COMSOL_MCP_HTTP_PORT", "8765"))
URL = f"http://{HOST}:{PORT}/mcp"
LOG_DIR = ROOT / "logs"
PID_FILE = LOG_DIR / "comsol_mcp_sidecar.pid"
STARTUP_TIMEOUT = int(os.environ.get("COMSOL_MCP_SIDECAR_TIMEOUT", "180"))

app = Server("COMSOL MCP")


def _sidecar_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("COMSOL_MCP_HTTP_HOST", HOST)
    env.setdefault("COMSOL_MCP_HTTP_PORT", str(PORT))
    return env


def _start_sidecar() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / "comsol_mcp_sidecar.log"
    log = log_path.open("ab")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [sys.executable, "-m", "src.http_server"],
        cwd=str(ROOT),
        env=_sidecar_env(),
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        creationflags=creationflags,
    )
    PID_FILE.write_text(str(process.pid), encoding="ascii")


async def _with_http_session(callback: Callable[[ClientSession], Awaitable[T]]) -> T:
    async with streamablehttp_client(URL, timeout=30, sse_read_timeout=300) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await callback(session)


async def _is_ready() -> bool:
    try:
        await _with_http_session(lambda session: session.list_tools())
        return True
    except Exception:
        return False


async def _ensure_sidecar() -> None:
    if await _is_ready():
        return

    _start_sidecar()
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if await _is_ready():
            return
        await anyio.sleep(1)

    raise RuntimeError(f"COMSOL MCP HTTP sidecar did not start at {URL}")


async def _forward(callback: Callable[[ClientSession], Awaitable[T]]) -> T:
    await _ensure_sidecar()
    return await _with_http_session(callback)


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    result = await _forward(lambda session: session.list_tools())
    return result.tools


@app.call_tool(validate_input=False)
async def call_tool(name: str, arguments: dict) -> types.CallToolResult:
    return await _forward(lambda session: session.call_tool(name, arguments))


@app.list_resources()
async def list_resources() -> list[types.Resource]:
    result = await _forward(lambda session: session.list_resources())
    return result.resources


@app.list_resource_templates()
async def list_resource_templates() -> list[types.ResourceTemplate]:
    result = await _forward(lambda session: session.list_resource_templates())
    return result.resourceTemplates


@app.read_resource()
async def read_resource(uri) -> list[ReadResourceContents]:
    result = await _forward(lambda session: session.read_resource(uri))
    contents: list[ReadResourceContents] = []
    for item in result.contents:
        if isinstance(item, types.TextResourceContents):
            contents.append(ReadResourceContents(item.text, item.mimeType))
        elif isinstance(item, types.BlobResourceContents):
            contents.append(ReadResourceContents(base64.b64decode(item.blob), item.mimeType))
    return contents


async def amain() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
