# -*- coding: utf-8 -*-
"""护栏:输入(防注入)、授权(防越权)、输出(PII 脱敏)。"""
import re
from data import ORDERS

INJECTION = ["忽略以上", "忽略之前", "ignore previous", "ignore above", "你现在是", "扮演"]

def input_guard(text):
    """输入护栏:拦截明显的提示注入。返回 (是否放行, 提示)。"""
    low = text.lower()
    if any(k.lower() in low for k in INJECTION):
        return False, "⚠️ 检测到可疑指令(疑似提示注入),已拦截。"
    return True, ""

def authz_guard(user_id, order_id):
    """授权护栏:校验订单是否属于当前用户(防越权)。"""
    o = ORDERS.get(order_id)
    if not o:
        return False, "未找到该订单。"
    if o["user"] != user_id:
        return False, "⚠️ 无权操作该订单(订单不属于当前用户),已拒绝。"
    return True, ""

def pii_mask(text):
    """输出护栏:手机号脱敏。"""
    return re.sub(r"(1[3-9]\d)\d{4}(\d{4})", r"\1****\2", text or "")
