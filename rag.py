# -*- coding: utf-8 -*-
"""
极简但"真实"的 RAG 检索:用 numpy 实现字符级 n-gram 的 TF 向量 + 余弦相似度。
- 零依赖(只用 numpy),离线可跑,适合课堂理解"向量化—检索"的本质。
- 生产中把 _vectorize 换成嵌入模型(如 bge-small-zh)即可,检索框架不变。
"""
try:
    import numpy as np
except ModuleNotFoundError:
    np = None
from data import POLICIES

def _ngrams(text, n=(1, 2)):
    text = text.replace(" ", "")
    grams = []
    for k in n:
        grams += [text[i:i+k] for i in range(len(text)-k+1)]
    return grams

class VectorStore:
    def __init__(self, docs: dict):
        self.ids = list(docs.keys())
        self.texts = list(docs.values())
        # 建词表
        vocab = {}
        for t in self.texts:
            for g in _ngrams(t):
                vocab.setdefault(g, len(vocab))
        self.vocab = vocab
        # 文档向量矩阵 (n_docs, vocab)
        if np:
            self.M = np.zeros((len(self.texts), len(vocab)), dtype=np.float32)
            for i, t in enumerate(self.texts):
                for g in _ngrams(t):
                    self.M[i, vocab[g]] += 1.0
            self._norm = np.linalg.norm(self.M, axis=1) + 1e-8
        else:
            self.M = [[0.0 for _ in vocab] for _ in self.texts]
            for i, t in enumerate(self.texts):
                for g in _ngrams(t):
                    self.M[i][vocab[g]] += 1.0
            self._norm = [(sum(x * x for x in row) ** 0.5) + 1e-8 for row in self.M]

    def _vectorize(self, q):
        if np:
            v = np.zeros(len(self.vocab), dtype=np.float32)
            for g in _ngrams(q):
                if g in self.vocab:
                    v[self.vocab[g]] += 1.0
            return v
        v = [0.0 for _ in self.vocab]
        for g in _ngrams(q):
            if g in self.vocab:
                v[self.vocab[g]] += 1.0
        return v

    def search(self, query, k=2):
        v = self._vectorize(query)
        if np:
            sims = (self.M @ v) / (self._norm * (np.linalg.norm(v) + 1e-8))
            order = np.argsort(-sims)[:k]
            return [(self.ids[i], self.texts[i], float(sims[i])) for i in order if sims[i] > 0]
        v_norm = (sum(x * x for x in v) ** 0.5) + 1e-8
        sims = []
        for i, row in enumerate(self.M):
            dot = sum(a * b for a, b in zip(row, v))
            sims.append(dot / (self._norm[i] * v_norm))
        order = sorted(range(len(sims)), key=lambda i: -sims[i])[:k]
        return [(self.ids[i], self.texts[i], float(sims[i])) for i in order if sims[i] > 0]

# 全局知识库(用政策原料构建)
KB = VectorStore(POLICIES)

def retrieve(query, k=2):
    """返回最相关的 k 段政策文本(纯文本列表),供 Agent 拼入提示。"""
    return [t for _id, t, s in KB.search(query, k)]

def retrieve_scored(query, k=3):
    """返回 (标题, 文本, 相似度),用于演示检索排序。"""
    return KB.search(query, k)

if __name__ == "__main__":
    for q in ["外卖超时了有没有补偿", "耳机能退货吗", "怎么开发票"]:
        print(f"\n问:{q}")
        for _id, txt, s in retrieve_scored(q, 2):
            print(f"  [{s:.3f}] {_id}: {txt}")
