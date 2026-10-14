# Process log

## 1. AI tools used

- Cursor, running Grok. I used it for the initial scaffold, and again any time a server refused to start or the model chose the wrong tool.
- The app is FastAPI and Uvicorn, with Pydantic on the request body. The agent is LangChain `create_agent` on LangGraph, and the session memory is LangGraph `MemorySaver`. Tool discovery and calls go through `langchain-mcp-adapters`.
- The model is NVIDIA NIM, `nvidia/nemotron-3.5-lightning-30b-a3b`, through `ChatNVIDIA`.
- MCP servers: `@modelcontextprotocol/server-filesystem`, `tavily-mcp`, `mcp-server-sqlite` (the catalog is SQLite), and `weather-open-meteo-mcp`. The image is Docker, deployed on Cloud Run.

## 2. Development narrative

I started by asking Cursor for a scaffold: "Build a research notebook on FastAPI and LangGraph. POST /chat should search with Tavily, write markdown under notes/, and keep the thread with MemorySaver keyed by session_id." It gave me main.py, agent.py and an MCP client, all on the OpenAI client. That same evening I switched models with this: "Use ChatNVIDIA when NVIDIA_API_KEY is set, leave the key in .env, and fall back to OpenAI only if that key is missing." I copied the NIM sample settings (temperature 1, thinking on), since the OpenAI client wasn't the right fit for my key.

The SQLite catalog is where I lost the most time. The assignment says to install @modelcontextprotocol/server-sqlite from npm, but that package doesn't exist, so I used mcp-server-sqlite 2025.4.25 from PyPI. It still wouldn't start on Windows, since the exe sits at .venv\Scripts\mcp-server-sqlite.exe and the stdio client only checks PATH. I told Cursor: "Start the sqlite server from the venv Scripts path, not from PATH." npx had the same problem, so filesystem and Tavily now run through cmd.exe /c npx. After that, "what have I saved" kept getting answered from the chat history instead of the database, so I changed the prompt: catalog questions must call sqlite, and "find this and keep it" must search, write the note, and insert a row before replying.

Near the end, the Cloud Run URL showed a blank page, so I made GET / redirect to /docs. The model also started acting like a generic chatbot and sending weather questions to Tavily, so I rewrote the prompt again. The line that stuck: "A weather question uses the Open-Meteo server only. Do not call Tavily, and do not answer today's weather from memory." I then pinned weather-open-meteo-mcp at 0.1.2 and redeployed as revision csci599-a1-00002-rch.

## 3. Verification narrative

One good chat response wasn't enough for me, so I tried several kinds of questions. "What is the Model Context Protocol?" gets a plain definition with no tool call. "Search for recent writing on tool-using agents" calls Tavily. "What is the weather in Los Angeles today?" goes to the weather server, using weather_weather-get_hourly or weather_weather-get_daily, and never touches Tavily.

To check memory, I used session_id demo-1, asked what an MCP server is, then asked "What did I just ask you?" with the same id. The follow-up names my first question and makes no tool call. The same follow-up under demo-2 has no idea what happened in demo-1. MemorySaver only lasts while the process is running, so a fresh Cloud Run instance (which is what min-instances 0 gives you after sitting idle) starts out empty.

The full chain is "Search for LangGraph checkpointers, save a note, and record the source." It searches, writes a file under notes/, then runs sqlite_write_query, and the reply gives the file path and the catalog row. I also ran python -m unittest discover -s tests, which covers the Windows npx wrapper, skipping Tavily when its key is missing, the weather server needing no key, and the sources table getting created.

For error handling, I asked it to read notes/does-not-exist.md. The filesystem server returns an error, my wrapper turns it into a tool message, and POST /chat still returns 200 with {"response": "..."} saying the file is missing, with no traceback. If a server fails at startup, the others still load, and GET /health lists the failed one under unavailable while status stays ok. A blank query or session_id gets a 422 from the request model. While the process is still starting, /chat returns 503 with {"response": "The agent is not ready yet."}.

## 4. What you learned

Cursor kept pushing the npm package the assignment names, and I only found out that @modelcontextprotocol/server-sqlite was never published by checking the registry and the official servers repo myself, which led me to the Python mcp-server-sqlite and the Windows problem where the stdio client can't find it unless I launch it from the venv Scripts path. Listing the tools was also not enough to make the model use them correctly, so I had to write the routing rules into the system prompt myself (catalog questions must call sqlite, weather must skip Tavily) and read the real prefixed tool names off GET /health, since they didn't match the package readme. The part no tool worked out for me was the deployment: MemorySaver lives inside one process, so I had to reason through why Cloud Run with min-instances 0 wipes a conversation after a cold start, and then confirm that with separate session ids instead of assuming memory was durable.
