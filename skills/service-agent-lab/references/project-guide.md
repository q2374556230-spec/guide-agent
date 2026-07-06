# Project Guide

## Project Purpose

`service-agent-lab` is a course project for a service-engineering assistant in a campus e-commerce scenario. The original system already supports order query, logistics query, ordinary product consulting, aftersale BPMN, ReAct tools, Web trace, and evaluation. The added innovation is an evidence-based shopping guide Agent: give the LLM a shopping toolset, collect product evidence, and let the model reason over that evidence for personalized purchase decisions.

## Runtime Architecture

- `agent.py`: top-level orchestration, intent routing, expert dispatch, ReAct path, and shopping expert decision logic.
- `llm.py`: real/mock LLM abstraction. Real mode uses OpenAI-compatible API settings; mock/rules mode keeps the demo stable without a key.
- `tools.py`: tool contracts and service/demo-data fallbacks for orders, logistics, products, refund, and recommendation.
- `shopping_research_agent.py`: enhanced shopping guide Agent with requirement parsing, fixed evidence-tool chain, real-LLM reasoning, and fallback rules.
- `data.py`: demo data including `PRODUCTS_EXT`, which provides review summaries, risk points, monthly sales, store scores, and aftersale scores.
- `bpmn_engine.py` and `bpmn_handlers.py`: BPMN execution for original aftersale flow.
- `shopping_bpmn_handlers.py` and `flows/shopping_guide.bpmn`: experiment-three validation only, not the Web guide path.
- `flows/shopping_research_agent_report.bpmn`: report-only overview diagram of the complete system.
- `web/index.html`: Web demo entry and trace display. Keep one official guide button, `AI导购：蓝牙耳机`.
- `evaluate.py`: regression/evaluation entry. Keep passing.

## Routing Contracts

Aftersale:

```text
orchestrate -> router -> expert_aftersale -> run_aftersale -> bpmn_engine.run_bpmn(flows/aftersale.bpmn)
```

Examples that must still work:

- `我要对订单20260601001申请退款`
- `订单20260601001什么时候到？超时有补偿吗？`
- `蓝牙耳机多少钱？`

Enhanced shopping guide:

```text
orchestrate -> router/expert_shopping -> _is_purchase_decision -> shopping_research_agent -> evidence tools -> real LLM reasoning or fallback rules
```

Canonical demo input:

```text
我想买一个300元以内的蓝牙耳机，主要在宿舍和图书馆用，想要降噪好一点，别漏音，续航别太差
```

## Shopping Guide Toolset

The current enhanced guide uses a fixed tool chain. The LLM does not dynamically choose tools yet.

1. `collect_product_candidates(text, parsed_need)`: search candidates from `tools.search_products` / product-service-like data.
2. `collect_review_summary(candidates)`: collect `review_summary` and `risk_points` from demo evidence.
3. `collect_sales_signal(candidates)`: collect `monthly_sales`, `rating`, and `price`.
4. `collect_store_profile(candidates)`: collect `store_name`, `store_score`, and `aftersale_score`.

The evidence package must include:

- `user_need`
- `parsed_need`
- `candidates`
- `review_summary`
- `sales_signal`
- `store_profile`
- `risk_points`
- `source_note`

Every evidence item should carry a `source` such as `demo_data`, `product_service`, or `fallback`.

## Real LLM and Fallback

When `OPENAI_API_KEY` exists and `llm.chat()` succeeds, the guide should use real LLM reasoning in two places:

- understand the user need when possible;
- generate recommendations from the evidence package.

When no key exists, the SDK is missing, the API returns invalid data, or evidence is empty, fallback to:

```python
tools.recommend_products(text, user_id=user_id)
```

The trace should explicitly state fallback:

```text
[导购] 真实LLM不可用，回退到规则推荐
```

For OpenAI-compatible providers, typical env vars are:

```text
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://.../v1
OPENAI_MODEL=...
```

If the response is HTML, the base URL is probably a dashboard URL instead of a `/v1` API endpoint.

## Report Language

Use this phrasing for the core innovation:

```text
本项目在保留原有订单、物流、商品咨询和售后 BPMN 能力的基础上，新增了基于证据的个性化导购 Agent。系统并非直接让大模型凭空推荐，而是为 LLM 配备候选商品检索、评价摘要收集、销量热度信号收集、店铺与售后信息收集等工具，先构造 evidence 证据包，再由真实大模型围绕用户预算、场景、偏好和避雷点进行推荐推理。在未配置真实 API 或调用失败时，系统自动回退到规则推荐，保证演示稳定性。
```

## Screenshot Checklist

Capture these for reports or defenses:

- Web page with the single `AI导购：蓝牙耳机` button.
- Shopping trace showing the evidence-tool chain and real LLM or fallback mode.
- Final shopping answer with Top3, risks, not-recommended item, scenes, and data-source note.
- Simple product query showing original path still works.
- Aftersale request showing original BPMN path still works.
- `python evaluate.py` passing.
- `flows/shopping_research_agent_report.bpmn` opened as the full-system process diagram.

## Do Not Do

- Do not crawl Taobao/JD for the demo unless the user explicitly asks and legal/compliance boundaries are addressed.
- Do not create a second Web shopping-guide entry for BPMN.
- Do not overwrite `.env` or print secrets.
- Do not change unrelated `__pycache__` artifacts intentionally.
- Do not weaken fallback behavior; the demo must run without a real API key.
