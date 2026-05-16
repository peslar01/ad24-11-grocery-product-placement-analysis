"""
defs_aisle_network.py — Aisle-level market basket analysis
==========================================================

This module replaces the original *product-level* co-purchase analysis
(see ../eda/defs_graph_plot.py) with an *aisle-level* one.

Why aisle level?
    The top products on Instacart are overwhelmingly fresh produce, while
    categories like pasta or snacks are split across hundreds of separate
    SKUs — so none of them individually reaches the top of the ranking and
    no "pasta cluster" or "snack cluster" can form. Grouping every product
    into its aisle (134 aisles) removes that fragmentation: every pasta SKU
    becomes one strong "dry pasta" node, every chip SKU one "chips pretzels"
    node, and the co-purchase structure becomes interpretable.

Pipeline:
    compute_aisle_pairs()  -> count how often each pair of aisles co-occurs
    build_edges()          -> keep pairs with a high enough lift
    giant_component()      -> drop disconnected stragglers
    detect_communities()   -> weighted greedy-modularity clustering (CNM)
    spring_layout()        -> 2D force-directed layout (community-aware)
    build_figure()         -> interactive Plotly network
    cluster_summary()      -> aisles grouped by cluster, for display
"""

from itertools import combinations
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

# community colour palette (matches the presentation deck)
PALETTE = ["#2F6E4F", "#E07A3F", "#5B8DB8", "#C9A227",
           "#8E5572", "#6FB07F", "#B0573A", "#3F7C85"]


# ---------------------------------------------------------------------------
# 1. Count aisle co-purchase pairs  (the one heavy step — cache it in the app)
# ---------------------------------------------------------------------------
def compute_aisle_pairs(data_dir):
    """
    Count, for every pair of aisles, in how many orders both appear.

    Returns:
        pairs    dict {(aisle_a, aisle_b): co_occurrence_count}
        count_a  dict {aisle_id: number of orders containing that aisle}
        n_orders int   total number of orders
        aid2name dict {aisle_id: aisle name}
    """
    data_dir = Path(data_dir)

    products = pd.read_csv(data_dir / "products.csv",
                           usecols=["product_id", "aisle_id"])
    aisles = pd.read_csv(data_dir / "aisles.csv")
    aid2name = dict(zip(aisles["aisle_id"], aisles["aisle"]))
    pid2aid = dict(zip(products["product_id"], products["aisle_id"]))

    # one row per (order, product) -> map to aisle -> one row per (order, aisle)
    op = pd.read_csv(data_dir / "order_products__prior.csv",
                     usecols=["order_id", "product_id"],
                     dtype={"order_id": "int32", "product_id": "int32"})
    op["aisle_id"] = op["product_id"].map(pid2aid).astype("int16")
    op = op[["order_id", "aisle_id"]].drop_duplicates()

    n_orders = int(op["order_id"].nunique())
    count_a = {int(k): int(v)
               for k, v in op.groupby("aisle_id")["order_id"].size().items()}

    # for each order, every pair of distinct aisles it contains
    grouped = op.groupby("order_id")["aisle_id"].agg(list)
    pairs = Counter()
    for ais in grouped:
        if len(ais) < 2:
            continue
        for a, b in combinations(sorted(set(ais)), 2):
            pairs[(int(a), int(b))] += 1

    return dict(pairs), count_a, n_orders, aid2name


# ---------------------------------------------------------------------------
# 2. Lift edges
# ---------------------------------------------------------------------------
def build_edges(pairs, count_a, n_orders, aid2name,
                min_count=2000, min_lift=1.3):
    """
    Keep aisle pairs that are bought together more than chance would predict.

    lift = P(A and B) / (P(A) * P(B))
         = count_ab * N / (count_a * count_b)

    lift > 1  -> positive association (bought together more than expected)
    """
    drop = {aid for aid, nm in aid2name.items() if nm in ("missing", "other")}
    edges = []
    for (a, b), c in pairs.items():
        if a in drop or b in drop or c < min_count:
            continue
        lift = c * n_orders / (count_a[a] * count_a[b])
        if lift >= min_lift:
            edges.append((a, b, float(lift)))
    return edges


# ---------------------------------------------------------------------------
# 3. Largest connected component
# ---------------------------------------------------------------------------
def giant_component(edges):
    """Return (node_set, edges) for the largest connected component."""
    adj = defaultdict(set)
    for a, b, _ in edges:
        adj[a].add(b)
        adj[b].add(a)

    seen, comps = set(), []
    for start in adj:
        if start in seen:
            continue
        stack, comp = [start], []
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            comp.append(x)
            stack.extend(adj[x] - seen)
        comps.append(comp)

    if not comps:
        return set(), []
    giant = set(max(comps, key=len))
    return giant, [(a, b, w) for a, b, w in edges if a in giant and b in giant]


# ---------------------------------------------------------------------------
# 4. Community detection — weighted greedy modularity (Clauset-Newman-Moore)
# ---------------------------------------------------------------------------
def detect_communities(nodes, edges):
    """Return {aisle_id: cluster_index}, clusters ordered largest-first."""
    idx = {n: i for i, n in enumerate(nodes)}
    n = len(nodes)
    if n == 0:
        return {}

    W = np.zeros((n, n))
    for a, b, w in edges:
        W[idx[a], idx[b]] += w
        W[idx[b], idx[a]] += w

    m2 = W.sum()
    if m2 == 0:
        return {nd: 0 for nd in nodes}

    k = W.sum(axis=1)
    comm = {i: {i} for i in range(n)}
    a_c = {i: k[i] for i in range(n)}
    e = defaultdict(lambda: defaultdict(float))
    for i in range(n):
        for j in range(n):
            if W[i, j]:
                e[i][j] += W[i, j]

    def best_merge():
        best, bx, by = 1e-12, None, None
        for x in list(e.keys()):
            for y, exy in e[x].items():
                if y <= x:
                    continue
                dq = 2 * (exy / m2 - (a_c[x] / m2) * (a_c[y] / m2))
                if dq > best:
                    best, bx, by = dq, x, y
        return best, bx, by

    while True:
        _, x, y = best_merge()
        if x is None:
            break
        comm[x] |= comm[y]
        a_c[x] += a_c[y]
        for z, w in list(e[y].items()):
            if z in (x, y):
                continue
            e[x][z] += w
            e[z][x] += w
            del e[z][y]
        e[x].pop(y, None)
        e[x].pop(x, None)
        del e[y]
        del comm[y]
        a_c.pop(y, None)

    communities = sorted(comm.values(), key=len, reverse=True)
    node_comm = {}
    for ci, members in enumerate(communities):
        for li in members:
            node_comm[nodes[li]] = ci
    return node_comm


# ---------------------------------------------------------------------------
# 5. Force-directed layout (community-aware: pull within-cluster, barely across)
# ---------------------------------------------------------------------------
def spring_layout(nodes, edges, node_comm, seed=7, iterations=400):
    """Return {aisle_id: np.array([x, y])} in roughly [-1, 1]."""
    rng = np.random.default_rng(seed)
    idx = {n: i for i, n in enumerate(nodes)}
    n = len(nodes)
    if n == 0:
        return {}

    ncomm = (max(node_comm.values()) + 1) if node_comm else 1
    pos = np.zeros((n, 2))
    for i, nd in enumerate(nodes):
        ci = node_comm.get(nd, 0)
        ang = 2 * np.pi * ci / max(ncomm, 1)
        pos[i] = [0.72 * np.cos(ang) + rng.normal(0, 0.26),
                  0.72 * np.sin(ang) + rng.normal(0, 0.26)]

    if not edges:
        return {nd: pos[i] for i, nd in enumerate(nodes)}

    EU = np.array([idx[a] for a, b, _ in edges])
    EV = np.array([idx[b] for a, b, _ in edges])
    EW = np.array([w for _, _, w in edges])
    EWn = 0.35 + 1.65 * (EW - EW.min()) / (np.ptp(EW) + 1e-9)
    same = np.array([node_comm.get(a) == node_comm.get(b)
                     for a, b, _ in edges])
    attract = np.where(same, 1.0, 0.12) * EWn

    k_opt = 2.0 / np.sqrt(max(n, 2))
    for it in range(iterations):
        t = 0.05 * (1 - it / iterations)
        disp = np.zeros((n, 2))
        diff = pos[:, None, :] - pos[None, :, :]
        dist = np.sqrt((diff ** 2).sum(-1)) + 1e-9
        rep = (k_opt ** 2) / dist
        np.fill_diagonal(rep, 0)
        disp += (diff / dist[..., None] * rep[..., None]).sum(1)

        d = pos[EU] - pos[EV]
        dd = np.sqrt((d ** 2).sum(-1)) + 1e-9
        f = (dd ** 2) / k_opt * attract
        force = d / dd[:, None] * f[:, None]
        np.add.at(disp, EU, -force)
        np.add.at(disp, EV, force)

        dl = np.sqrt((disp ** 2).sum(-1)) + 1e-9
        pos += disp / dl[:, None] * np.minimum(dl, t)[:, None]
        pos -= pos.mean(0)

    pos /= np.abs(pos).max() + 1e-9
    return {nd: pos[i] for i, nd in enumerate(nodes)}


# ---------------------------------------------------------------------------
# 6. Interactive Plotly figure
# ---------------------------------------------------------------------------
def build_figure(nodes, edges, node_comm, pos, count_a, aid2name):
    """Build an interactive 2D network figure of the aisle co-purchase graph."""
    import plotly.graph_objects as go

    fig = go.Figure()

    # edges (drawn first, underneath)
    ex, ey = [], []
    for a, b, _ in edges:
        ex += [pos[a][0], pos[b][0], None]
        ey += [pos[a][1], pos[b][1], None]
    fig.add_trace(go.Scatter(
        x=ex, y=ey, mode="lines",
        line=dict(color="rgba(150,165,155,0.40)", width=1),
        hoverinfo="skip", showlegend=False,
    ))

    # nodes — one trace per community so each gets its own colour + legend entry
    ncomm = (max(node_comm.values()) + 1) if node_comm else 1
    max_count = max(count_a.values()) if count_a else 1
    for ci in range(ncomm):
        members = [nd for nd in nodes if node_comm.get(nd) == ci]
        if not members:
            continue
        fig.add_trace(go.Scatter(
            x=[pos[nd][0] for nd in members],
            y=[pos[nd][1] for nd in members],
            mode="markers+text",
            text=[aid2name[nd] for nd in members],
            textposition="top center",
            textfont=dict(size=9, color="#1C2E22"),
            marker=dict(
                size=[14 + 40 * (count_a[nd] / max_count) for nd in members],
                color=PALETTE[ci % len(PALETTE)],
                line=dict(color="white", width=1.2),
            ),
            name=f"Cluster {ci + 1}",
            customdata=[count_a[nd] for nd in members],
            hovertemplate="<b>%{text}</b><br>"
                          "appears in %{customdata:,} orders<extra></extra>",
        ))

    fig.update_layout(
        showlegend=True,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False, scaleanchor="x", scaleratio=1),
        margin=dict(l=0, r=0, t=10, b=0),
        height=640,
        plot_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.0,
                    xanchor="left", x=0),
    )
    return fig


# ---------------------------------------------------------------------------
# 7. Cluster summary (aisles grouped by cluster, ordered by order-coverage)
# ---------------------------------------------------------------------------
def cluster_summary(nodes, node_comm, count_a, aid2name):
    """Return a list of dicts: {cluster, colour, size, aisles[]} largest-first."""
    ncomm = (max(node_comm.values()) + 1) if node_comm else 0
    out = []
    for ci in range(ncomm):
        members = [nd for nd in nodes if node_comm.get(nd) == ci]
        if not members:
            continue
        members.sort(key=lambda nd: -count_a[nd])
        out.append({
            "cluster": ci + 1,
            "colour": PALETTE[ci % len(PALETTE)],
            "size": len(members),
            "aisles": [aid2name[nd] for nd in members],
        })
    return out
