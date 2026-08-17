"""Run the fleet + registry as in-process uvicorn servers.

Keeps the whole lab in one process (no port races, easy start/stop) while
still going through real HTTP/A2A network calls.
"""

from __future__ import annotations

import asyncio
import logging

import uvicorn

from .a2a_client import check_health, fetch_card
from .config import HOST, REGISTRY_PORT, REGISTRY_URL
from .fleet import AgentSpec, build_fleet
from .registry_server import Registry, build_registry_app
from .server import build_a2a_app

logger = logging.getLogger("discovery_lab.launch")


class FleetRuntime:
    """Owns one sub-agent server (and the directory) inside this process."""

    def __init__(self) -> None:
        self._apps: dict[str, object] = {}
        self._servers: dict[str, uvicorn.Server] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._registry_app = None
        self._registry_server: uvicorn.Server | None = None

    # ------------------------------------------------------------------
    async def start_registry(self) -> None:
        registry = Registry()
        app = build_registry_app(registry)
        # seed from the fleet specs so the directory is authoritative
        for spec in build_fleet():
            try:
                registry.register(await fetch_card(spec.url))
            except Exception as exc:
                logger.warning("registry seed failed for %s: %s", spec.name, exc)
        self._registry_app = app
        self._registry_server = await self._start(app, REGISTRY_PORT)
        await self._wait_ready(REGISTRY_URL)

    async def start_agent(self, spec: AgentSpec) -> None:
        app = build_a2a_app(spec)
        self._apps[spec.name] = app
        server = await self._start(app, spec.port)
        self._servers[spec.name] = server
        await self._wait_ready(spec.url)
        logger.info("agent %s ready on %s", spec.name, spec.url)

    async def start_fleet(self) -> None:
        for spec in build_fleet():
            await self.start_agent(spec)

    async def stop_agent(self, name: str) -> None:
        server = self._servers.pop(name, None)
        task = self._tasks.pop(name, None)
        if server:
            await server.shutdown()
        if task:
            task.cancel()
        self._apps.pop(name, None)
        logger.info("agent %s stopped", name)

    async def stop(self) -> None:
        for name in list(self._servers):
            await self.stop_agent(name)
        if self._registry_server:
            await self._registry_server.shutdown()
        logger.info("fleet runtime stopped")

    # ------------------------------------------------------------------
    async def _start(self, app, port: int) -> uvicorn.Server:
        config = uvicorn.Config(app, host=HOST, port=port, log_level="warning")
        server = uvicorn.Server(config)
        task = asyncio.create_task(server.serve())
        self._tasks[f"port:{port}"] = task
        return server

    async def _wait_ready(self, base_url: str, timeout: float = 10.0) -> None:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if await check_health(base_url, timeout=1.0):
                return
            await asyncio.sleep(0.1)
        raise RuntimeError(f"server at {base_url} did not become ready")