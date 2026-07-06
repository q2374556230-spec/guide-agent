# -*- coding: utf-8 -*-
"""
统一的大模型客户端。

设计要点(重要):
- 对外暴露与 OpenAI 完全一致的接口:client.chat.completions.create(model, messages, tools, ...)
  返回对象 .choices[0].message,message 有 .content 与 .tool_calls。
- 若环境变量里配置了 OPENAI_API_KEY,则使用真实的 OpenAI 兼容大模型(openai SDK)。
- 否则回退到 MockLLM —— 一个确定性的"教学桩",用规则模拟大模型的"意图判断/工具选择/
  生成回复",让整套系统在【无密钥、无网络】的情况下也能完整跑通、输出可复现。
  学生在自己电脑上 `export OPENAI_API_KEY=...` 后,同一套代码即调用真实模型,无需改动。

这正是工程上的"接口隔离":上层 Agent/编排逻辑只依赖接口,不关心背后是真模型还是桩。
"""
import os, re, json, uuid

def _load_dotenv():
    """无依赖加载同目录下的 .env(每行 KEY=VALUE),已存在的环境变量不覆盖。
    这就是配置大模型 API Key 的地方:把 .env.example 复制成 .env 并填入 key。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:                       # 空值不设置,避免空字符串误判为"已配置"
            os.environ.setdefault(k.strip(), v)

_load_dotenv()

CHAT_MODEL = os.getenv("CHAT_MODEL", "mock-llm")

# ----------------------------------------------------------------------
# 模拟 OpenAI 返回对象的最小数据结构
# ----------------------------------------------------------------------
class _Fn:
    def __init__(self, name, arguments): self.name = name; self.arguments = arguments
class _ToolCall:
    def __init__(self, name, args):
        self.id = "call_" + uuid.uuid4().hex[:8]; self.type = "function"
        self.function = _Fn(name, json.dumps(args, ensure_ascii=False))
class _Msg:
    def __init__(self, content=None, tool_calls=None, role="assistant"):
        self.content = content; self.tool_calls = tool_calls or None; self.role = role
    def model_dump(self):
        d = {"role": self.role, "content": self.content or ""}
        if self.tool_calls:
            d["tool_calls"] = [{"id": tc.id, "type": "function",
                                "function": {"name": tc.function.name,
                                             "arguments": tc.function.arguments}}
                               for tc in self.tool_calls]
        return d
class _Choice:
    def __init__(self, m): self.message = m
class _Resp:
    def __init__(self, m): self.choices = [_Choice(m)]


def _norm(messages):
    """把 messages 里可能混入的对象统一成 dict,便于桩解析。"""
    out = []
    for m in messages:
        if isinstance(m, dict): out.append(m)
        elif hasattr(m, "model_dump"): out.append(m.model_dump())
        else: out.append({"role": getattr(m, "role", "assistant"),
                          "content": getattr(m, "content", "")})
    return out


# ----------------------------------------------------------------------
# MockLLM:确定性教学桩
# ----------------------------------------------------------------------
class _MockCompletions:
    def create(self, model=None, messages=None, tools=None,
               temperature=0, response_format=None, **kw):
        msgs = _norm(messages)
        sys_txt = " ".join(m.get("content", "") or "" for m in msgs if m.get("role") == "system")
        user_txt = " ".join(m.get("content", "") or "" for m in msgs if m.get("role") == "user")

        # 1) 路由:system 要求"只回一个词"
        if "只回一个词" in sys_txt or "只回复一个词" in sys_txt:
            return _Resp(_Msg(content=self._route(user_txt)))

        # 2) 摘要压缩:system/user 要求"压缩成要点"
        if "压缩成要点" in sys_txt + user_txt or "压缩成" in user_txt:
            return _Resp(_Msg(content=self._summarize(user_txt)))

        # 3) 评测打分:judge,要求输出 {"pass": ...}
        if response_format and '"pass"' in (sys_txt + user_txt):
            return _Resp(_Msg(content=self._judge(user_txt)))

        # 4) 意图识别:要求输出 {"intent": ...}
        if response_format and ("意图" in sys_txt or '"intent"' in sys_txt):
            return _Resp(_Msg(content=self._intent(user_txt)))

        # 5) 工具调用 / ReAct:提供了 tools。决策以"当前(最后一条)用户消息"为准,
        #    历史仅作背景,避免把上一轮诉求误带入本轮。
        if tools:
            last_user = next((m.get("content", "") for m in reversed(msgs)
                              if m.get("role") == "user"), user_txt)
            return self._tool_step(msgs, tools, last_user)

        # 6) 兜底:普通生成
        return _Resp(_Msg(content=self._final_answer(msgs, user_txt)))

    # ---- 子能力 ----
    def _route(self, t):
        if re.search(r"退|赔|补偿|售后|发票|换货", t): return "售后"
        if re.search(r"到哪|物流|配送|送到|快递|多久|什么时候到", t): return "物流"
        if re.search(r"多少钱|价格|库存|有货|推荐|买|商品", t): return "导购"
        return "其他"

    def _summarize(self, t):
        oid = "、".join(set(re.findall(r"\d{8,}", t)))
        kw = [k for k in ["退款", "退货", "超时", "补偿", "地址", "发票", "换货"] if k in t]
        parts = []
        if oid: parts.append(f"涉及订单 {oid}")
        if kw: parts.append("诉求关键词:" + "/".join(kw))
        return ";".join(parts) if parts else "用户进行了若干轮咨询。"

    def _judge(self, t):
        # 从 "要点:[...]" 与 "回答:..." 中判断要点是否被覆盖
        m_must = re.search(r"要点[:：]\s*(\[[^\]]*\])", t)
        m_ans = re.search(r"回答[:：]\s*(.+)", t, re.S)
        must, ans = [], ""
        if m_must:
            try: must = json.loads(m_must.group(1).replace("'", '"'))
            except Exception: must = re.findall(r"[\"']([^\"']+)[\"']", m_must.group(1))
        if m_ans: ans = m_ans.group(1)
        ok = all(str(x) in ans for x in must) if must else True
        return json.dumps({"pass": bool(ok)}, ensure_ascii=False)

    def _intent(self, t):
        if re.search(r"退|赔|补偿|售后|发票|换货", t): intent = "退款售后"
        elif re.search(r"到哪|物流|配送|快递|多久|什么时候到", t): intent = "查物流"
        elif re.search(r"多少钱|价格|库存|有货", t): intent = "商品咨询"
        elif re.search(r"订单|查一下|状态", t): intent = "查订单"
        else: intent = "其他"
        ent = {}
        oid = re.findall(r"\d{8,}", t)
        if oid: ent["order_id"] = oid[0]
        for p in ["蓝牙耳机", "黄焖鸡米饭", "麻辣烫", "机械键盘"]:
            if p in t: ent["product"] = p
        return json.dumps({"intent": intent, "entities": ent}, ensure_ascii=False)

    def _called_tools(self, msgs):
        names = []
        for m in msgs:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                names += [tc["function"]["name"] for tc in m["tool_calls"]]
        return names

    def _observations(self, msgs):
        obs = []
        for m in msgs:
            if m.get("role") == "tool":
                try: obs.append(json.loads(m["content"]))
                except Exception: obs.append(m["content"])
        return obs

    def _tool_step(self, msgs, tools, user_txt):
        """ReAct 决策:已有观察则决定下一步,信息齐全则给最终答案。"""
        avail = {t["function"]["name"] for t in tools}
        called = self._called_tools(msgs)
        oid_list = re.findall(r"\d{8,}", user_txt)
        oid = oid_list[0] if oid_list else None
        wants_status = bool(re.search(r"到哪|物流|配送|状态|送到|什么时候|订单", user_txt))
        wants_policy = bool(re.search(r"超时|补偿|退|赔|政策|发票|换货", user_txt))
        wants_product = bool(re.search(r"多少钱|价格|库存|有货", user_txt))

        # 第一步:查订单/物流
        if oid and wants_status and "query_order" in avail and "query_order" not in called:
            return _Resp(_Msg(tool_calls=[_ToolCall("query_order", {"order_id": oid})]))
        if oid and wants_status and "query_order" not in avail \
           and "track_logistics" in avail and "track_logistics" not in called:
            return _Resp(_Msg(tool_calls=[_ToolCall("track_logistics", {"order_id": oid})]))
        # 下一步:查政策(ReAct 多步的体现)
        if wants_policy and "search_policy" in avail and "search_policy" not in called:
            q = "超时补偿" if re.search(r"超时|补偿", user_txt) else user_txt
            return _Resp(_Msg(tool_calls=[_ToolCall("search_policy", {"q": q})]))
        # 商品查询
        if wants_product and "query_product" in avail and "query_product" not in called:
            prod = next((p for p in ["蓝牙耳机", "黄焖鸡米饭", "麻辣烫", "机械键盘"] if p in user_txt), "蓝牙耳机")
            return _Resp(_Msg(tool_calls=[_ToolCall("query_product", {"name": prod})]))
        # 信息齐全 → 终态回复
        return _Resp(_Msg(content=self._final_answer(msgs, user_txt)))

    def _final_answer(self, msgs, user_txt):
        obs = self._observations(msgs)
        order = next((o for o in obs if isinstance(o, dict) and "status" in o), None)
        policy = next((o for o in obs if isinstance(o, list)), None)
        product = next((o for o in obs if isinstance(o, dict) and "price" in o and "status" not in o), None)
        parts = []
        if order and "error" not in order:
            seg = f"您的订单{order.get('order_id','')}当前状态:{order.get('status')}"
            if order.get("eta"): seg += f",预计{order.get('eta')}"
            if order.get("rider"): seg += f",骑手{order.get('rider')}"
            if order.get("tracking"): seg += f",快递单号{order.get('tracking')}({order.get('carrier','')})"
            parts.append(seg + "。")
        if policy:
            parts.append("相关政策:" + "；".join(policy))
        if product and "error" not in product:
            parts.append(f"{product['name']}售价{product['price']}元,库存{product['stock']}件,评分{product['rating']}。")
        if any(isinstance(o, dict) and o.get("error") for o in obs):
            parts.append("抱歉,未能查询到对应信息,请核对后再试。")
        if not parts:
            parts.append("您好,我可以帮您查订单、查物流、查商品或处理售后,请问需要什么?")
        return "".join(parts)


class _MockChat:
    def __init__(self): self.completions = _MockCompletions()
class MockLLM:
    def __init__(self): self.chat = _MockChat()


# ----------------------------------------------------------------------
# 对外:client + chat() 便捷函数(真实/桩 自动切换)
# ----------------------------------------------------------------------
if os.getenv("OPENAI_API_KEY"):
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"),
                    base_url=os.getenv("OPENAI_BASE_URL"))
    BACKEND = "real:" + CHAT_MODEL
else:
    client = MockLLM()
    BACKEND = "mock-llm(教学桩,离线可复现)"


def chat(messages, **kw):
    """无工具的便捷调用,返回 message 对象。"""
    resp = client.chat.completions.create(model=CHAT_MODEL, messages=messages, **kw)
    return _coerce_message(resp)


def _coerce_message(resp):
    """兼容不同 OpenAI-compatible 服务的返回形态。

    标准 SDK 返回 ChatCompletion(.choices[0].message); 少数兼容服务/代理可能
    直接返回字符串或 dict。上层统一只依赖 message.content。
    """
    if hasattr(resp, "choices"):
        return resp.choices[0].message
    if isinstance(resp, str):
        if _looks_like_html(resp):
            raise ValueError("LLM API 返回了 HTML 页面,请检查 OPENAI_BASE_URL 是否为 /v1 API 地址")
        return _Msg(content=resp)
    if isinstance(resp, dict):
        choices = resp.get("choices") or []
        if choices:
            choice = choices[0]
            msg = choice.get("message") if isinstance(choice, dict) else None
            if isinstance(msg, dict):
                return _Msg(content=msg.get("content", ""), tool_calls=msg.get("tool_calls"))
            if isinstance(msg, str):
                return _Msg(content=msg)
            text = choice.get("text") if isinstance(choice, dict) else None
            if text is not None:
                return _Msg(content=text)
        if "content" in resp:
            content = resp.get("content", "")
            if _looks_like_html(content):
                raise ValueError("LLM API 返回了 HTML 页面,请检查 OPENAI_BASE_URL 是否为 /v1 API 地址")
            return _Msg(content=content)
        if "text" in resp:
            content = resp.get("text", "")
            if _looks_like_html(content):
                raise ValueError("LLM API 返回了 HTML 页面,请检查 OPENAI_BASE_URL 是否为 /v1 API 地址")
            return _Msg(content=content)
    content = str(resp)
    if _looks_like_html(content):
        raise ValueError("LLM API 返回了 HTML 页面,请检查 OPENAI_BASE_URL 是否为 /v1 API 地址")
    return _Msg(content=content)


def _looks_like_html(text):
    if not isinstance(text, str):
        return False
    head = text.lstrip()[:200].lower()
    return head.startswith("<!doctype html") or head.startswith("<html") or "<div id=\"root\"" in head


if __name__ == "__main__":
    print("当前后端:", BACKEND)
    print(chat([{"role": "user", "content": "你好"}]).content)
