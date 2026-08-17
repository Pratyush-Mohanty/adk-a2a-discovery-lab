"""Turn a fleet AgentSpec into a real A2A HTTP server (FastAPI + a2a-sdk).

Serves:
  * the Agent Card at  /.well-known/agent-card.json
  * JSON-RPC at        /a2a/jsonrpc   (message/send, tasks/*, ...)
  * REST at            /a2a/rest

We implement the A2A `AgentExecutor` interface directly (no LLM) so the
sub-agents run deterministically and offline.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from a2a.helpers import new_task_from_user_message
from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
    create_rest_routes,
)
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCard, AgentCapabilities, AgentInterface, AgentSkill, Part, TaskState
from fastapi import FastAPI

from .config import AGENT_BASE_LATENCY_MS, AgentSpec

if TYPE_CHECKING:
    from a2a.server.agent_execution.context import RequestContext
    from a2a.server.events.event_queue import EventQueue

logger = logging.getLogger("discovery_lab.server")


def build_agent_card(spec: AgentSpec) -> AgentCard:
    """Construct the proto AgentCard a sub-agent advertises."""
    card = AgentCard(
        name=spec.name,
        description=spec.description,
        version="1.0.0",
        supported_interfaces=[
            AgentInterface(
                url=spec.url + "a2a/jsonrpc",
                protocol_binding="JSONRPC",
                protocol_version="1.0",
            ),
            AgentInterface(
                url=spec.url + "a2a/rest",
                protocol_binding="HTTP+JSON",
                protocol_version="1.0",
            ),
        ],
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain", "application/json"],
    )
    for s in spec.skills:
        card.skills.append(
            AgentSkill(
                id=s.id,
                name=s.name,
                description=s.description,
                tags=list(s.tags),
                examples=list(s.examples),
            )
        )
    return card


class SkillAgentExecutor(AgentExecutor):
    """Deterministic executor that runs the spec's handler function."""

    def __init__(self, spec: AgentSpec) -> None:
        self._spec = spec
        self._fn = spec.handler

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        user_text = context.get_user_input() or ""

        task = context.current_task
        if not task and context.message:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        task_id = task.id if task else context.task_id
        updater = TaskUpdater(event_queue, task_id, context.context_id)
        await updater.start_work()

        try:
            await asyncio.sleep(AGENT_BASE_LATENCY_MS / 1000.0)
            result = self._fn(user_text)
            await updater.complete(
                message=updater.new_agent_message([Part(text=str(result))])
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("executor failed for %s", self._spec.name)
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=updater.new_agent_message([Part(text=f"agent error: {exc}")]),
            )

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.update_status(state=TaskState.TASK_STATE_CANCELED)


def build_a2a_app(spec: AgentSpec) -> FastAPI:
    """Build a FastAPI app exposing the agent over A2A."""
    card = build_agent_card(spec)
    task_store = InMemoryTaskStore()
    handler = DefaultRequestHandler(
        agent_executor=SkillAgentExecutor(spec),
        task_store=task_store,
        agent_card=card,
    )

    jsonrpc_routes = create_jsonrpc_routes(
        request_handler=handler,
        rpc_url="/a2a/jsonrpc",
    )
    rest_routes = create_rest_routes(
        request_handler=handler,
        path_prefix="/a2a/rest",
    )
    card_routes = create_agent_card_routes(agent_card=card)

    app = FastAPI(title=spec.name)
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=card_routes,
        jsonrpc_routes=jsonrpc_routes,
        rest_routes=rest_routes,
    )
    return app