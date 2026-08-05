# Simple Deep Agent Architecture

## Goal

Build a minimal LangChain Deep Agent style backend for Olist e-commerce dispute
resolution. The agent receives a user question, calls deterministic CSV tools,
applies `EC_POLICY_V2`, and writes JSON outputs.

## Agents

```text
User question
  -> LangChain create_agent graph
  -> Coordinator Agent
  -> Olist CSV tools
  -> Filesystem/Shell backend
  -> Policy Engine
  -> Output Writer + Trace Logger
```

## Tool Access

- `investigate_case(case_id)`: reads `input/EC_*.json`, loads the claimed
  order, calculates all required fields, writes `output/EC_*.json`.
- `investigate_order(order_id)`: investigates a raw Olist order ID without
  needing an input file.
- `run_all_cases()`: processes all 50 input cases.

## Data Flow

1. Load `.env` using the keys from `.env.example`.
2. Load CSV files from `data/`.
3. Join order, customer, item, product, payment, and seller context.
4. Calculate delivery variance, seller handoff variance, and payment
   reconciliation.
5. Apply policy rules in priority order.
6. Build evidence IDs only from CSV-backed entities.
7. Write output JSON and append one trace record.

## Runtime

`app.lakeagent.build_agent()` creates a real `create_agent(...)` graph with
model, tools, system prompt, middleware, and the name
`lakeagent_retrieval_agent`. The backend is `LocalShellBackend(root_dir=repo)`,
so the agent can use filesystem tools and execute code inside the repo root.
