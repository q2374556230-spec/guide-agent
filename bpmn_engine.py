# -*- coding: utf-8 -*-
"""
极简 BPMN 执行引擎(只用标准库 xml.etree)。
作用:把学生在 bpmn.io 画的 .bpmn 文件【真正加载并执行】——
     按 开始事件→任务→网关(条件分支)→结束事件 的顺序走,
     每个"任务"绑定一个 Python 处理器(去调微服务 / RAG / 退款)。
这就是"业务流程建模(BPMN)如何集成进系统"的答案:流程图不是画着看的,是驱动执行的。
"""
import xml.etree.ElementTree as ET

def _ln(tag):            # 去掉命名空间,取本地名
    return tag.split('}')[-1]

def load_bpmn(path):
    """解析 .bpmn,返回 (节点表, 顺序流列表, 开始节点id)。"""
    root = ET.parse(path).getroot()
    proc = next(e for e in root.iter() if _ln(e.tag) == 'process')
    nodes, flows, start = {}, [], None
    for e in proc:
        t = _ln(e.tag)
        if t == 'sequenceFlow':
            cond = None
            for c in e:
                if _ln(c.tag) == 'conditionExpression':
                    cond = (c.text or '').strip()
            flows.append({'id': e.get('id'), 'src': e.get('sourceRef'),
                          'tgt': e.get('targetRef'), 'name': e.get('name'), 'cond': cond})
        elif t in ('startEvent', 'endEvent', 'task', 'serviceTask',
                   'userTask', 'exclusiveGateway'):
            # 读取【节点上配置的实现引用】:camunda:delegateExpression / class / expression
            # 这就是在 BPMN 节点上"配置函数名/类名"的标准位置(Camunda/Flowable 同理)。
            impl = None
            for k, v in e.attrib.items():
                if _ln(k) in ('delegateExpression', 'class', 'expression'):
                    impl = v.strip().strip('${} ')   # ${h_query_order} → h_query_order
                    break
            nodes[e.get('id')] = {'type': t, 'name': e.get('name') or e.get('id'), 'impl': impl}
            if t == 'startEvent':
                start = e.get('id')
    return nodes, flows, start

def _out(flows, nid):
    return [f for f in flows if f['src'] == nid]

def run_bpmn(path, handlers, ctx, log=print, max_steps=50):
    """按 BPMN 流程执行。
    handlers: {实现名(delegateExpression): func(ctx)->str};兼容用 节点id/名称 作 key。
    任务节点优先用【节点上配置的实现引用 impl】去查处理器,这才是引擎的标准做法。"""
    nodes, flows, cur = load_bpmn(path)
    log(f"▶ 开始:{nodes[cur]['name']}")
    cur = _out(flows, cur)[0]['tgt']
    for _ in range(max_steps):
        nd = nodes[cur]; t = nd['type']
        if t == 'endEvent':
            log(f"■ 结束:{nd['name']}")
            return ctx
        if t in ('task', 'serviceTask', 'userTask'):
            impl = nd.get('impl')
            h = (handlers.get(impl) if impl else None) or handlers.get(cur) or handlers.get(nd['name'])
            msg = h(ctx) if h else "(节点未配置实现,跳过)"
            tag = f"〔impl={impl}〕" if impl else ""
            log(f"任务「{nd['name']}」{tag}→ {msg}")
            cur = _out(flows, cur)[0]['tgt']
        elif t == 'exclusiveGateway':
            outs = _out(flows, cur)
            chosen = default = None
            for f in outs:
                if not f['cond']:
                    default = f; continue
                expr = f['cond'].replace('${', '').replace('}', '').strip()
                try:
                    if eval(expr, {"__builtins__": {}}, ctx):
                        chosen = f; break
                except Exception:
                    pass
            chosen = chosen or default or outs[0]
            log(f"网关「{nd['name']}」→ 选择分支「{chosen.get('name') or '默认'}」")
            cur = chosen['tgt']
        else:
            cur = _out(flows, cur)[0]['tgt']
    return ctx
