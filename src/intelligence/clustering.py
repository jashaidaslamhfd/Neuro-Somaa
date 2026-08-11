#!/usr/bin/env python3
"""Topic clustering — TF-IDF + k-means++ in pure numpy.

Groups channel videos by topic/title terms, then reports per-cluster real
performance so the content team sees WHICH micro-themes pay off, not just
single lucky videos. k adapts to data size and results below the sample bar
are clearly marked exploratory.
"""
from __future__ import annotations

import math
import re

_STOP = set("""le la les un une des du de ce cet cette et ou est sont dans pour
avec sans mais donc car quand que qui quoi pourquoi comment votre vos ton ta tes
au aux on se ne pas plus très the a an of to in on and or""".split())


def _tokens(text: str) -> list[str]:
    # ligatures œ/æ kept: "cœur" must survive as one token (it tops this niche)
    return [t for t in re.findall(r"[a-zà-ÿœæ']+", text.lower()) if len(t) > 2 and t not in _STOP]


def cluster_topics(history: list[dict], max_k: int = 6, seed: int = 5) -> dict:
    import numpy as np

    docs = [(f"{e.get('topic','')} {e.get('title','')}", e) for e in (history or [])
            if e.get("views") is not None]
    n = len(docs)
    if n < 12:
        return {"reliable": False, "reason": f"n={n} too small for clustering", "clusters": []}

    # vocabulary = top terms by document frequency
    df: dict[str, int] = {}
    doc_tokens: list[list[str]] = []
    for text, _ in docs:
        toks = _tokens(text)
        doc_tokens.append(toks)
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    vocab = [t for t, _ in sorted(df.items(), key=lambda kv: -kv[1])[:150]]
    index = {t: i for i, t in enumerate(vocab)}
    n_docs = n
    X = np.zeros((n_docs, len(vocab)))
    for i, toks in enumerate(doc_tokens):
        for t in toks:
            if t in index:
                X[i, index[t]] += 1
    # tf-idf + L2 normalize
    idf = np.array([math.log((1 + n_docs) / (1 + df[t])) + 1 for t in vocab])
    X *= idf
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    X /= norms

    k = max(2, min(max_k, n // 8))
    rng = np.random.default_rng(seed)
    # k-means++ initialization on unit sphere
    centroids = [X[rng.integers(n)]]
    for _ in range(k - 1):
        d2 = np.min(1 - X @ np.array(centroids).T, axis=1)  # cosine distance
        probs = np.maximum(d2, 0) ** 2
        centroids.append(X[rng.choice(n, p=probs / probs.sum())])
    C = np.array(centroids)
    labels = -np.ones(n, dtype=int)  # -1 forces ≥1 real assignment pass
    for _ in range(30):
        sims = X @ C.T
        new_labels = sims.argmax(axis=1)
        if (new_labels == labels).all():
            break
        labels = new_labels
        for j in range(k):
            members = X[labels == j]
            if len(members):
                C[j] = members.mean(axis=0)
                C[j] /= max(np.linalg.norm(C[j]), 1e-9)
            else:
                # empty cluster → reseed it on the currently worst-served point
                worst = int(np.argmax(-sims.max(axis=1)))
                C[j] = X[worst]

    clusters = []
    for j in range(k):
        members = [docs[i] for i in range(n) if labels[i] == j]
        if not members:
            continue
        views = [int(m[1].get("views") or 0) for m in members]
        # top terms by summed tf-idf inside cluster
        colsum = X[[i for i in range(n) if labels[i] == j]].sum(axis=0)
        top_idx = colsum.argsort()[::-1][:5]
        clusters.append({
            "cluster_id": j,
            "name": " / ".join(vocab[i] for i in top_idx if colsum[i] > 0) or f"cluster {j}",
            "size": len(members),
            "avg_views": round(sum(views) / len(views), 1),
            "max_views": max(views),
            "examples": [m[1].get("title", "")[:60] for m in members[:3]],
        })
    clusters.sort(key=lambda c: -c["avg_views"])
    return {
        "reliable": True,
        "method": "TF-IDF + spherical k-means++",
        "k": k, "n": n,
        "clusters": clusters,
        "winner_cluster": clusters[0]["name"] if clusters else None,
        "honesty": "clusters are exploratory at this n; re-run monthly as data grows.",
    }
