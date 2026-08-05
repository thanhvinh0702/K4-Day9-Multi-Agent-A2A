# Simple LangChain Agent Runtime Backend

## Env

Create `.env` from `.env.example`:

```bash
OPENROUTER_API_KEY=sk-or-v1-...
LLM_MODEL=openai/gpt-4o-mini
```

## Install optional agent dependencies

```bash
python3 -m pip install -r requirements.txt
```

These packages are required for the real `create_agent(...)` runtime backend.

## Run Agent

```bash
python3 -m app.lakeagent "investigate EC_001"
```

## Generate README Outputs

```bash
python3 -m app.run_outputs
```

This writes `output/EC_001.json` ... `output/EC_050.json`, plus root-level
`trace.jsonl` and `metadata.json`.

## Generate with LLM Agent

```bash
python3 -m app.run_llm_outputs
```

This calls `create_agent(...)` for each case, uses tool calling, and writes the
structured outputs.

## Useful Questions

```bash
python3 -m app.lakeagent "investigate EC_001"
python3 -m app.lakeagent "investigate order 9b75cdaf2d85857ef023980e15d01546"
python3 -m app.lakeagent "run all 50 cases"
```

The agent is built with:

```python
agent = create_agent(
    model=model,
    tools=tools,
    system_prompt=build_system_prompt(...),
    middleware=[
        FilesystemMiddleware(backend=backend),
        SummarizationMiddleware(model=model),
        TodoListMiddleware(),
    ],
    name="lakeagent_retrieval_agent",
)
```
