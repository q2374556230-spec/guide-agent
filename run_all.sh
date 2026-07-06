#!/usr/bin/env bash
# 一键启动微服务并跑通四个实验的全部演示
set -e
cd "$(dirname "$0")"

echo ">>> 启动微服务 (8001/8002/8003)"
python3 services/order_service.py &  P1=$!
python3 services/product_service.py & P2=$!
python3 services/logistics_service.py & P3=$!
sleep 1.5
trap "kill $P1 $P2 $P3 2>/dev/null" EXIT

echo; echo "########## 实验1:意图识别 ##########"
python3 -c "from agent import detect_intent
for q in ['我的黄焖鸡到哪了','20260601002想退款','蓝牙耳机多少钱','在吗']:
    print(f'{q} -> {detect_intent(q)}')"

echo; echo "########## 实验2:ReAct 自主多步 ##########"
python3 -c "from agent import react_agent
print(react_agent('订单20260601001什么时候到?要是超时了有没有补偿?'))"

echo; echo "########## 实验3:RAG + 多Agent ##########"
python3 rag.py
python3 -c "from agent import orchestrate
for q in ['订单20260601002的物流到哪了','外卖超时有补偿吗','机械键盘多少钱']:
    print(q,'->',orchestrate(q,verbose=False)['answer'])"

echo; echo "########## 实验4:护栏 + 评测 + 集成 ##########"
python3 evaluate.py
python3 app.py
echo; echo ">>> 全部完成"
