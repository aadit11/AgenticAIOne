# Process log

Write this file in your own voice after you have run the agent. The rubric treats a log that reads as generated as weak evidence. Replace every section below. Do not submit these prompts.

## 1. AI tools used

List each assistant you actually used, and the version if you know it. Examples the assignment names: Claude, ChatGPT, Gemini, Grok, GitHub Copilot, Cursor, local Ollama.

- 

## 2. Development narrative

200–300 words, in order. What you tried, what failed, where you got stuck, and how you got unstuck. Quote specific prompts that produced code or a fix you kept.

## 3. Verification narrative

How you tested past a single happy-path request. Cover at least:

- a question that should not call a tool
- a search that should call Tavily
- a follow-up in the same `session_id` that should use memory, and a second `session_id` that should not see that history
- one query that chains two or more tools
- a missing file or a stopped MCP server, and what the HTTP response was

## 4. What you learned

Two or three sentences on something the assistant could not settle and you had to check yourself. Startup logs, a real `tools/list` result, or a failed deploy count. A summary of the assignment does not.
