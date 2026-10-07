"""HTTP entrypoint for the research notebook agent."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
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
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")
    from agent import build_agent

    app.state.runtime = await build_agent()
    logger.info(
        "agent ready tools=%s unavailable=%s",
        app.state.runtime.tool_names,
        app.state.runtime.unavailable,
    )
    yield


app = FastAPI(title="Research Notebook Agent", lifespan=lifespan)


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
