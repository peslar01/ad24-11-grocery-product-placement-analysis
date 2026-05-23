"""
defs_aisle_network.py — Aisle-level market basket analysis
==========================================================

This module performs *aisle-level* co-purchase / market basket analysis.

Why aisle level?
    The top products on Instacart are overwhelmingly fresh produce, while
    categories like pasta or snacks are split across hundreds of separate
    SKUs, so none of them individually reaches the top of the ranking and
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
def spring_layout(nodes, edges, node_comm, seed=7, iterations=400, dim=2):
    """Force-directed layout in 2D or 3D.

    Returns {aisle_id: np.array([...])} of length `dim`, scaled to ~[-1, 1].
    The community-aware initialisation places clusters at different angles
    around the centre so the force-directed pass converges cleanly.
    """
    if dim not in (2, 3):
        raise ValueError("dim must be 2 or 3")
    rng = np.random.default_rng(seed)
    idx = {n: i for i, n in enumerate(nodes)}
    n = len(nodes)
    if n == 0:
        return {}

    ncomm = (max(node_comm.values()) + 1) if node_comm else 1
    pos = np.zeros((n, dim))
    for i, nd in enumerate(nodes):
        ci = node_comm.get(nd, 0)
        if dim == 2:
            ang = 2 * np.pi * ci / max(ncomm, 1)
            pos[i] = [0.72 * np.cos(ang) + rng.normal(0, 0.26),
                      0.72 * np.sin(ang) + rng.normal(0, 0.26)]
        else:
            # Fibonacci-sphere init so clusters spread around the unit sphere.
            phi = np.arccos(1 - 2 * (ci + 0.5) / max(ncomm, 1))
            theta = np.pi * (1 + 5 ** 0.5) * ci
            pos[i] = [
                0.72 * np.sin(phi) * np.cos(theta) + rng.normal(0, 0.18),
                0.72 * np.sin(phi) * np.sin(theta) + rng.normal(0, 0.18),
                0.72 * np.cos(phi)                  + rng.normal(0, 0.18),
            ]

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
        disp = np.zeros((n, dim))
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
# 6. Dynamic cluster naming  (from dominant departments)
# ---------------------------------------------------------------------------
def name_clusters(nodes, node_comm, aisle_info):
    """Derive a human-readable name per cluster from its dominant departments.

    Heuristics (applied to the *order-weighted* department mix of the cluster):
        - if one department covers ≥ 60 %  →  "{dept}-led"
        - if top 2 cover ≥ 70 %             →  "{dept1} + {dept2}"
        - otherwise                         →  "mixed: {dept1} + {dept2} + {dept3}"

    Returns {cluster_idx: str}.
    """
    if not node_comm or aisle_info is None:
        return {}

    ncomm = max(node_comm.values()) + 1
    names = {}
    for ci in range(ncomm):
        members = [nd for nd in nodes if node_comm.get(nd) == ci]
        if not members:
            continue
        # weight each department by the aisle's purchase count (its weight in the cluster)
        weights = defaultdict(float)
        for nd in members:
            info = aisle_info.get(int(nd))
            if info is None:
                continue
            weights[info["department"]] += float(info.get("share_pct", 1.0))

        total = sum(weights.values()) or 1.0
        ranked = sorted(weights.items(), key=lambda kv: -kv[1])
        if not ranked:
            names[ci] = f"Cluster {ci + 1}"
            continue

        top1_share = ranked[0][1] / total
        top2_share = sum(w for _, w in ranked[:2]) / total

        if top1_share >= 0.60:
            names[ci] = f"{ranked[0][0]}-led"
        elif len(ranked) >= 2 and top2_share >= 0.70:
            names[ci] = f"{ranked[0][0]} + {ranked[1][0]}"
        else:
            top3 = " + ".join(d for d, _ in ranked[:3])
            names[ci] = f"mixed: {top3}"
    return names


# ---------------------------------------------------------------------------
# 7. Interactive Plotly figure (with lift-weighted edges + optional focus)
# ---------------------------------------------------------------------------
def build_figure(nodes, edges, node_comm, pos, count_a, aid2name,
                 aisle_info=None, cluster_names=None, focus_aisle_id=None,
                 label_top_n=20):
    """Build an interactive 2D *or* 3D network figure of the aisle co-purchase graph.

    aisle_info       optional {aisle_id: {department, share_pct, reorder_rate}}
                     , used to enrich the node hover tooltip.
    cluster_names    optional {cluster_idx: str}, used as the legend label.
    focus_aisle_id   if given, edges *not* connected to this aisle and nodes
                     *not* in its 1-hop neighbourhood are visually dimmed.
    label_top_n      show text labels only on this many largest aisles (the
                     focused aisle + its neighbours are always labelled).
                     Reduces the "60 overlapping labels" mess.
    """
    import plotly.graph_objects as go

    aisle_info = aisle_info or {}
    cluster_names = cluster_names or {}

    # Detect dimensionality from the first position vector (2D or 3D).
    sample = next(iter(pos.values())) if pos else None
    is_3d = sample is not None and len(sample) == 3
    Scatter = go.Scatter3d if is_3d else go.Scatter

    # ── Compute focus neighbourhood ─────────────────────────────────────────
    if focus_aisle_id is not None:
        neighbours = set()
        for a, b, _ in edges:
            if a == focus_aisle_id:
                neighbours.add(b)
            elif b == focus_aisle_id:
                neighbours.add(a)
        focused_nodes = neighbours | {focus_aisle_id}
        is_focused_edge = lambda a, b: a == focus_aisle_id or b == focus_aisle_id
    else:
        focused_nodes = set(nodes)
        is_focused_edge = lambda a, b: True

    # ── Choose which nodes get a visible text label ─────────────────────────
    # All-labels-on is overwhelming once you have 60+ aisles. Label only the
    # biggest ones, plus anything in the focus set so the focused aisle and
    # its neighbours always remain readable.
    if label_top_n is not None and label_top_n < len(nodes):
        sorted_by_count = sorted(nodes, key=lambda nd: -count_a.get(nd, 0))
        labelled_set = set(sorted_by_count[:label_top_n])
    else:
        labelled_set = set(nodes)
    if focus_aisle_id is not None:
        labelled_set = labelled_set | focused_nodes

    def coord_axes(node_ids):
        out = {"x": [pos[n][0] for n in node_ids],
               "y": [pos[n][1] for n in node_ids]}
        if is_3d:
            out["z"] = [pos[n][2] for n in node_ids]
        return out

    def edge_axes(node_pairs):
        xs, ys, zs = [], [], []
        for a, b in node_pairs:
            xs += [pos[a][0], pos[b][0], None]
            ys += [pos[a][1], pos[b][1], None]
            if is_3d:
                zs += [pos[a][2], pos[b][2], None]
        out = {"x": xs, "y": ys}
        if is_3d:
            out["z"] = zs
        return out

    fig = go.Figure()

    # ── Edges, in three lift buckets so width encodes association strength ──
    if edges:
        lifts = [w for _, _, w in edges]
        l_min, l_max = min(lifts), max(lifts)
        t1 = l_min + (l_max - l_min) * 0.33
        t2 = l_min + (l_max - l_min) * 0.67

        buckets = [
            ("thin",   1.2, lambda w: w <= t1),
            ("medium", 2.4, lambda w: t1 < w <= t2),
            ("thick",  4.0, lambda w: w > t2),
        ]

        dim_pairs = [(a, b) for a, b, _ in edges if not is_focused_edge(a, b)]
        if dim_pairs:
            fig.add_trace(Scatter(
                **edge_axes(dim_pairs),
                mode="lines",
                line=dict(color="rgba(150,165,155,0.08)", width=1),
                hoverinfo="skip", showlegend=False,
            ))

        # Stronger edge contrast — especially needed in 3D where transparency
        # washes out very quickly. 2D is fine with a slightly softer line.
        edge_rgba = "rgba(80,95,85,0.70)" if is_3d else "rgba(110,125,115,0.55)"
        for label, width, pred in buckets:
            sel = [(a, b) for a, b, w in edges if pred(w) and is_focused_edge(a, b)]
            if sel:
                fig.add_trace(Scatter(
                    **edge_axes(sel),
                    mode="lines",
                    line=dict(color=edge_rgba, width=width),
                    hoverinfo="skip", showlegend=False,
                ))

    # ── Nodes — one trace per community ─────────────────────────────────────
    # In 2D we can pass a per-node opacity list. Scatter3d, however, only
    # accepts a scalar marker.opacity — so in 3D we split each cluster into a
    # "focused" sub-trace (opacity 1.0) and an "unfocused" sub-trace (0.18).
    ncomm = (max(node_comm.values()) + 1) if node_comm else 1
    max_count = max(count_a.values()) if count_a else 1

    def _build_node_trace(members, opacity_value, opacity_list, ci, legend_name,
                          show_in_legend):
        if not members:
            return None
        # Slightly bigger base size; in 3D Plotly renders markers a bit smaller
        # per-pixel than 2D, so we only mildly scale down (was 0.35×, too small).
        sizes = [14 + 44 * (count_a[nd] / max_count) for nd in members]
        if is_3d:
            sizes = [s * 0.75 for s in sizes]
        cdata = list(zip(
            [count_a[nd] for nd in members],
            [aisle_info.get(int(nd), {}).get("department",   "—") for nd in members],
            [aisle_info.get(int(nd), {}).get("share_pct",   0.0) for nd in members],
            [aisle_info.get(int(nd), {}).get("reorder_rate", 0.0) for nd in members],
        ))
        marker = dict(
            size=sizes,
            color=PALETTE[ci % len(PALETTE)],
            line=dict(color="white", width=1.2),
        )
        if is_3d:
            marker["opacity"] = opacity_value          # scalar — Scatter3d limitation
        else:
            marker["opacity"] = opacity_list           # per-point list — fine in 2D

        # Only top-N aisles get a visible label — empty string elsewhere.
        node_text = [aid2name[nd] if nd in labelled_set else "" for nd in members]

        kwargs = dict(
            **coord_axes(members),
            mode="markers+text",
            marker=marker,
            name=legend_name,
            showlegend=show_in_legend,
            customdata=cdata,
            hovertemplate=(
                "<b>%{customdata[4]}</b><br>"
                "Cluster: " + legend_name + "<br>"
                "Department: %{customdata[1]}<br>"
                "Appears in %{customdata[0]:,} orders<br>"
                "Share of all purchases: %{customdata[2]:.2f}%<br>"
                "Reorder rate: %{customdata[3]:.0%}"
                "<extra></extra>"
            ),
            text=node_text,
        )
        # Push the aisle name into customdata so the hover always shows it,
        # even on unlabelled nodes (text="" suppresses the on-chart label only).
        kwargs["customdata"] = [
            (c[0], c[1], c[2], c[3], aid2name[nd])
            for c, nd in zip(cdata, members)
        ]

        if is_3d:
            kwargs["textposition"] = "top center"
            kwargs["textfont"] = dict(size=11, color="#1C2E22")
        else:
            kwargs["textposition"] = "top center"
            kwargs["textfont"] = dict(size=9, color="#1C2E22")
        return kwargs

    for ci in range(ncomm):
        members = [nd for nd in nodes if node_comm.get(nd) == ci]
        if not members:
            continue
        legend_name = cluster_names.get(ci, f"Cluster {ci + 1}")

        if is_3d:
            focused_sub   = [nd for nd in members if nd in focused_nodes]
            unfocused_sub = [nd for nd in members if nd not in focused_nodes]
            # Show legend entry only on the focused sub-trace (avoid duplicates).
            t1 = _build_node_trace(focused_sub, 1.0, None, ci, legend_name,
                                   show_in_legend=True)
            t2 = _build_node_trace(unfocused_sub, 0.18, None, ci, legend_name,
                                   show_in_legend=(not focused_sub))
            for t in (t1, t2):
                if t is not None:
                    fig.add_trace(Scatter(**t))
        else:
            opacities = [1.0 if nd in focused_nodes else 0.18 for nd in members]
            kwargs = _build_node_trace(members, 1.0, opacities, ci, legend_name,
                                       show_in_legend=True)
            fig.add_trace(Scatter(**kwargs))

    if is_3d:
        fig.update_layout(
            showlegend=True,
            scene=dict(
                xaxis=dict(visible=False),
                yaxis=dict(visible=False),
                zaxis=dict(visible=False),
                aspectmode="data",
                bgcolor="white",
            ),
            margin=dict(l=0, r=0, t=10, b=0),
            height=680,
            legend=dict(orientation="h", yanchor="bottom", y=1.0,
                        xanchor="left", x=0),
        )
    else:
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
# 8. Cluster summary — aisles grouped by department, with dynamic names
# ---------------------------------------------------------------------------
def cluster_summary(nodes, node_comm, count_a, aid2name,
                    aisle_info=None, cluster_names=None):
    """Return a list of dicts describing each cluster.

    Each entry has:
        cluster        1-based index
        name           dynamic cluster name (e.g. "produce-led")
        colour         hex colour matching the chart
        size           number of aisles in the cluster
        by_department  list of (department, [aisle_names]) — aisles inside
                       the cluster grouped by department, departments ordered
                       by their share of the cluster's purchase volume.
        aisles         flat list of aisle names (largest-first), kept for
                       backwards compatibility.
    """
    aisle_info = aisle_info or {}
    cluster_names = cluster_names or {}

    ncomm = (max(node_comm.values()) + 1) if node_comm else 0
    out = []
    for ci in range(ncomm):
        members = [nd for nd in nodes if node_comm.get(nd) == ci]
        if not members:
            continue
        members.sort(key=lambda nd: -count_a[nd])

        # group by department, ordering departments by total aisle volume
        dept_to_aisles = defaultdict(list)
        dept_weight = defaultdict(int)
        for nd in members:
            dept = aisle_info.get(int(nd), {}).get("department", "—")
            dept_to_aisles[dept].append(aid2name[nd])
            dept_weight[dept] += count_a[nd]

        by_department = [
            (dept, dept_to_aisles[dept])
            for dept, _ in sorted(dept_weight.items(), key=lambda kv: -kv[1])
        ]

        out.append({
            "cluster":       ci + 1,
            "name":          cluster_names.get(ci, f"Cluster {ci + 1}"),
            "colour":        PALETTE[ci % len(PALETTE)],
            "size":          len(members),
            "by_department": by_department,
            "aisles":        [aid2name[nd] for nd in members],
        })
    return out
