"""HTTP entrypoint for the research notebook agent."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "What is an MCP server? Answer in two sentences.",
                "session_id": "demo",
            }
        }
    )

    query: str = Field(min_length=1)
    session_id: str = Field(min_length=1)

    @field_validator("query", "session_id")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped


class ChatResponse(BaseModel):
    response: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("NVIDIA_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set NVIDIA_API_KEY or OPENAI_API_KEY")
    from agent import build_agent

    app.state.runtime = await build_agent()
    logger.info(
        "agent ready tools=%s unavailable=%s",
        app.state.runtime.tool_names,
        app.state.runtime.unavailable,
    )
    yield


app = FastAPI(
    title="Research Notebook",
    description="Send a research question to POST /chat. Use the same session_id to continue a notebook thread.",
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
async def home() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health() -> dict:
    runtime = getattr(app.state, "runtime", None)
    if runtime is None:
        return {"status": "starting", "tools": [], "unavailable": []}
    return {
        "status": "ok",
        "tools": runtime.tool_names,
        "unavailable": runtime.unavailable,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse | JSONResponse:
    runtime = getattr(app.state, "runtime", None)
    if runtime is None:
        return JSONResponse(
            status_code=503,
            content={"response": "The agent is not ready yet."},
        )
    from agent import ask

    try:
        text = await ask(runtime, body.query, body.session_id)
    except Exception as exc:
        logger.exception("chat request failed session=%s", body.session_id)
        text = (
            "The agent hit an unexpected error and recovered without crashing. "
            f"Details: {exc}"
        )
    return ChatResponse(response=text)


def main() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
