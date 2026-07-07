# BPMN 怎么画 + 怎么集成进系统(专题)

> 解决两个问题:**(1) 学生不知道怎么画 BPMN;(2) 画完的 BPMN 怎么真正接入系统、驱动运行。**
> 本系统里 BPMN **不是画着看的装饰**——售后退款流程由 `flows/aftersale.bpmn` 这张图**实际驱动执行**:改图就改流程,不用改 Python。

---

## 一、先看最终效果(BPMN 真在跑)

用户在网页问“我要对订单20260601001申请售后退款”,系统加载 `aftersale.bpmn` 并按图执行,右侧 trace 实时显示走了哪条路径:

```
[路由] 判定意图 = 售后
  [BPMN] ▶ 开始:收到售后请求
  [BPMN] 任务「查询订单」→ 调订单+物流微服务 (状态=配送中, 金额=32.5, 超时=True)
  [BPMN] 网关「是否超时?」→ 选择分支「是」
  [BPMN] 任务「查超时补偿政策」→ RAG检索→ 外卖订单承诺30分钟内送达…
  [BPMN] 网关「金额≥100需人工?」→ 选择分支「否」
  [BPMN] 任务「自动发起退款」→ 已自动发起退款(状态=退款中)
  [BPMN] 任务「通知用户」→ 已通知用户
  [BPMN] ■ 结束
```

**换一个订单(199元、未超时),同一张图自动走另一条分支**——这就是流程图驱动的意义:

```
  [BPMN] 任务「查询订单」→ (状态=已发货, 金额=199.0, 超时=False)
  [BPMN] 网关「是否超时?」→ 选择分支「否」 → 查退款政策
  [BPMN] 网关「金额≥100需人工?」→ 选择分支「是」 → 人工审核
```

---

## 二、这张流程图长什么样

```
                          ┌─────────────────┐
                    是 →  │ 查超时补偿政策   │ ─┐
 ○ ──→ [查询订单] ──→ ◇ 是否超时?         │
开始              ╲    否 →  ┌─────────────┐  │   ◇ 金额≥100? 是→[人工审核]─┐
                            │ 查退款政策   │ ─┴──→  需人工?  否→[自动退款]─┤
                            └─────────────┘                              ├→[通知用户]→ ●
                                                                          ┘            结束
```

- 圆圈 ○ ● = **事件**(开始/结束)
- 圆角矩形 = **任务**(查询订单、查政策、人工审核、自动退款、通知)
- 菱形 ◇ = **排他网关**(二选一的判断:是否超时、金额是否需人工)

---

## 三、怎么画(bpmn.io,5 分钟)

1. 打开 **https://demo.bpmn.io**(在线,免安装;或下载桌面版 Camunda Modeler)。
2. 画布默认有一个“开始事件”圆圈,双击给它命名 `收到售后请求`。
3. 从左侧工具条拖元素:
   - 拖 **任务(圆角矩形)**:依次放 `查询订单`、`查超时补偿政策`、`查退款政策`、`人工审核`、`自动发起退款`、`通知用户`。
   - 拖 **排他网关(菱形)**:放 `是否超时?` 和 `金额≥100需人工?`。
   - 拖 **结束事件(圆圈)**:命名 `结束`。
4. **连线**:鼠标悬停某元素,边缘出现小箭头,拖到下一个元素即可连接。
5. **给网关的两条分支线命名**:点中分支线,在右侧属性面板把 Name 填 `是` / `否`。
6. **设条件**(关键):点中分支线 → 右侧属性面板 → `Condition Expression` 填:
   - “是否超时?”的“是”分支:`${timed_out == True}`
   - “金额≥100需人工?”的“是”分支:`${amount >= 100}`
   - “否”分支留空(作为默认分支)。
7. **设节点 Id**(关键,这是“图”与“代码”对接的钥匙):点中任务 → 属性面板 `General → Id`,改成与代码约定一致的 id,例如 `Task_QueryOrder`、`Task_AutoRefund`(见第四节对照表)。
8. 菜单 **Download / 导出**,得到 `.bpmn` 文件,保存为项目里的 `flows/aftersale.bpmn`,覆盖即可。

> 导出的 `.bpmn` 就是一段 XML(本项目已附一份可直接用)。它既能在 bpmn.io 里打开继续编辑,也能被下面的引擎直接执行。

---

## 四、怎么接进系统(三步接线)

### 第 1 步:引擎读 .bpmn 并按流程走(`bpmn_engine.py`)

引擎用标准库 `xml.etree` 解析 .bpmn,从开始事件出发,遇任务就调对应处理器,遇网关就按条件选分支:

```python
def run_bpmn(path, handlers, ctx, log=print, max_steps=50):
    nodes, flows, cur = load_bpmn(path)          # 解析 .bpmn
    cur = _out(flows, cur)[0]['tgt']             # 离开开始事件
    for _ in range(max_steps):
        nd = nodes[cur]; t = nd['type']
        if t == 'endEvent':
            log(f"■ 结束:{nd['name']}"); return ctx
        if t in ('task','serviceTask','userTask'):
            h = handlers.get(cur) or handlers.get(nd['name'])
            log(f"任务「{nd['name']}」→ {h(ctx)}")       # ← 执行该节点绑定的动作
            cur = _out(flows, cur)[0]['tgt']
        elif t == 'exclusiveGateway':
            outs = _out(flows, cur); chosen = default = None
            for f in outs:
                if not f['cond']: default = f; continue
                expr = f['cond'].replace('${','').replace('}','').strip()
                if eval(expr, {"__builtins__": {}}, ctx): chosen = f; break  # ← 按流程变量判断
            chosen = chosen or default or outs[0]
            log(f"网关「{nd['name']}」→ 分支「{chosen.get('name')}」")
            cur = chosen['tgt']
```

### 第 2 步:把每个节点 id 绑定到真实动作(`bpmn_handlers.py`)

**节点 id ←→ 处理器函数** 的对照,就是“图”与“系统”的接线表:

| BPMN 节点(图里画的) | 节点 Id | 绑定的处理器 | 真实动作 |
|---|---|---|---|
| 查询订单 | `Task_QueryOrder` | `h_query_order` | 调订单微服务 + 物流微服务,写入 `amount`、`timed_out` |
| 查超时补偿政策 | `Task_Compensation` | `h_compensation` | RAG 检索超时补偿政策 |
| 查退款政策 | `Task_RefundPolicy` | `h_refund_policy` | RAG 检索退款政策 |
| 人工审核 | `Task_ManualReview` | `h_manual_review` | 标记转人工 |
| 自动发起退款 | `Task_AutoRefund` | `h_auto_refund` | 调退款微服务 |
| 通知用户 | `Task_Notify` | `h_notify` | 汇总最终答复 |

```python
def h_query_order(ctx):                       # 节点"查询订单"的动作
    o = query_order(ctx["order_id"]); ctx["order"] = o
    ctx["amount"] = o.get("amount", 0)        # ← 写入流程变量,供后面网关判断
    ctx["timed_out"] = bool(track_logistics(ctx["order_id"]).get("timed_out"))
    return f"调订单+物流微服务 (金额={ctx['amount']}, 超时={ctx['timed_out']})"

HANDLERS = {                                  # id 对照表(必须与 .bpmn 里的 id 一致)
    "Task_QueryOrder": h_query_order,
    "Task_Compensation": h_compensation,
    "Task_AutoRefund": h_auto_refund, ...
}
```

> **网关条件怎么取到值?** 处理器把数据写进 `ctx`(如 `ctx['timed_out']`、`ctx['amount']`),网关的 `${timed_out == True}`、`${amount >= 100}` 就是在这个 `ctx` 上求值。所以**先有“查询订单”任务写入变量,后面的网关才能判断**——顺序由你在图里连线决定。

### 第 3 步:让 Agent 在“售后”意图时触发这条流程(`agent.py`)

```python
def expert_aftersale(text, ctx=None, verbose=False):
    oids = re.findall(r"\d{8,}", text)
    if oids:
        from bpmn_handlers import run_aftersale
        final, trace = run_aftersale(oids[0])     # ← 执行 aftersale.bpmn
        if verbose:
            for line in trace: print("  " + line) # ← trace 会显示在网页右侧面板
        return "【售后专家·BPMN流程】" + final
    return "【售后专家】" + react_agent(text, verbose=verbose, extra_msgs=ctx)
```

至此闭环:**网页对话 → 路由到“售后” → 加载 .bpmn → 引擎按图执行(调微服务/RAG/退款)→ 结果与流程轨迹返回前端**。

---

## 五、运行验证

```bash
# 启动微服务后,直接跑 BPMN 流程(两条分支)
python3 services/order_service.py & python3 services/product_service.py & \
python3 services/logistics_service.py & sleep 1
python3 bpmn_handlers.py
```

会打印订单 `20260601001`(超时、小额→自动退款)与 `20260601002`(未超时、大额→人工审核)两条**不同路径**,全部真实调用微服务。网页端 `python3 server.py` 后,发“对订单20260601001申请售后退款”,右侧 trace 面板就会显示上面第一节的流程轨迹。

---

## 六、学生练习:改流程不改代码

这才是 BPMN 集成的价值——**业务流程可视化地改,系统行为跟着变**:

1. 在 bpmn.io 打开 `flows/aftersale.bpmn`。
2. 在“通知用户”前加一个网关 `是否生鲜?`,“是”分支接一个新任务 `转质量赔付`(Id 设为 `Task_QualityClaim`)。
3. 在 `bpmn_handlers.py` 的 `HANDLERS` 里加一行 `"Task_QualityClaim": h_quality_claim` 并实现该函数。
4. 重新导出 .bpmn 覆盖,重跑 `python3 bpmn_handlers.py` —— 新分支立即生效。

> 体会:流程结构(先后、分支)在**图**里改;每个节点干什么在**处理器**里写。两者通过**节点 Id**对接,职责清晰,这就是 BPMN + 微服务 + Agent 的工程范式。
