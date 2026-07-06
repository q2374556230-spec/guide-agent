---
name: service-agent-lab
description: Maintain, extend, test, or explain the service-agent-lab project. Use this skill when working on the campus e-commerce service agent, shopping guide Agent, BPMN flows, ReAct/tool routing, real-LLM configuration, fallback behavior, Web trace demo, evaluation tests, or the course report for this repository.
---

# Service Agent Lab

Use this skill as the project playbook for `service-agent-lab`, a course project that preserves the original service assistant while adding an evidence-based shopping guide Agent.

## First Moves

1. Work from the repository root, usually `E:\service-agent-lab`.
2. Treat `.env` as secret-bearing. Check whether a key exists with boolean probes only; do not print API keys.
3. Preserve existing behavior before adding innovation. Do not remove order query, logistics query, ordinary product query, aftersale BPMN, ReAct tooling, Web trace, or `evaluate.py` coverage.
4. Read [references/project-guide.md](references/project-guide.md) before changing runtime routing, shopping guide behavior, BPMN files, or report/demo instructions.

## Safe Change Rules

- Keep `flows/shopping_guide.bpmn` as command-line/experiment validation only; do not wire it into the Web main path.
- Keep runtime aftersale flow on `flows/aftersale.bpmn`.
- Keep simple product questions such as `蓝牙耳机多少钱？` on the original product-query/ReAct path.
- Route purchase-decision questions such as `我想买一个300元以内的蓝牙耳机...` to `shopping_research_agent.shopping_research_agent`.
- Let real LLM calls use `llm.chat()` and OpenAI-compatible env vars; fallback must work without a real API key.
- Evidence for the enhanced guide should come from demo/product-service data unless the user explicitly asks for a live source extension.

## Required Verification

Run these checks after runtime changes:

```powershell
python -m py_compile agent.py tools.py shopping_research_agent.py evaluate.py
python -c "from shopping_research_agent import shopping_research_agent; r=shopping_research_agent('我想买一个300元以内的蓝牙耳机，图书馆用，重视降噪和续航，不想漏音'); print('\n'.join(r['trace'])); print(r['answer'])"
python -c "from agent import orchestrate; print(orchestrate('蓝牙耳机多少钱？', verbose=True))"
python -c "from agent import orchestrate; print(orchestrate('我想买一个300元以内的蓝牙耳机，图书馆用，重视降噪和续航，不想漏音', verbose=True))"
python evaluate.py
```

Use `.\.venv\Scripts\python.exe` instead of `python` when the active shell points at an incompatible Python.

## Demo Signals

For a successful enhanced shopping-guide demo, the trace should show:

- `[导购] 进入个性化导购 Agent`
- `[导购] 需求理解`
- `[工具] collect_product_candidates：检索候选商品`
- `[工具] collect_review_summary：收集评价摘要`
- `[工具] collect_sales_signal：收集销量信号`
- `[工具] collect_store_profile：收集店铺售后信息`
- `[导购] 构造 evidence 证据包`
- `[导购] 调用真实 LLM 基于证据推理` or `[导购] 真实LLM不可用，回退到规则推荐`

The final answer should contain Top3 recommendations, reasons, risks, not-recommended items, fit/unfit scenarios, and data-source notes.
