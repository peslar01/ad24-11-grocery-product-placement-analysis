"""
defs.py – Market Basket Analysis Hilfsfunktionen
=================================================
Verwendung im Notebook (graph-plot.ipynb):
    from defs import load_data, build_ranking, build_pairs,
                     build_confidence_rules, build_lift_rules,
                     build_lift_graph, get_coords, build_plot, detect_communities

Verwendung in Quarto (.qmd) aus einem anderen Ordner:
    import sys
    sys.path.append("../eda")
    from defs import load_data, build_ranking, ...
"""

import pandas as pd
from itertools import combinations
from collections import Counter

import networkx as nx
from networkx.algorithms.community import greedy_modularity_communities

import plotly.graph_objects as go


# ---------------------------------------------------------------------------
# Daten laden
# ---------------------------------------------------------------------------

def load_data(orders_path: str, order_products_path: str, products_path: str):
    """
    Lädt die drei CSV-Dateien und gibt einen gemergten DataFrame zurück.

    Returns:
        orders (DataFrame), data (DataFrame: order_products + products)
    """
    orders = pd.read_csv(orders_path)
    order_products = pd.read_csv(order_products_path)
    products = pd.read_csv(products_path)
    data = order_products.merge(products, on="product_id")
    return orders, data


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def build_ranking(data: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    """
    Erstellt ein Produkt-Ranking mit absolutem Vorkommen und prozentualem Anteil.

    Returns:
        DataFrame mit Spalten: Produkt, Anzahl, Share in %
    """
    product_counts = Counter(data["product_name"])
    ranking = pd.DataFrame(product_counts.most_common(), columns=["Produkt", "Anzahl"])
    total_orders = orders["order_id"].nunique()
    ranking["Share in %"] = (ranking["Anzahl"] / total_orders * 100).round(2).astype(float)
    return ranking


# ---------------------------------------------------------------------------
# Produktpaare zählen
# ---------------------------------------------------------------------------

def build_pairs(data: pd.DataFrame) -> Counter:
    """
    Zählt alle Produktpaare, die in derselben Bestellung vorkommen.

    Returns:
        Counter mit (Produkt A, Produkt B) → Anzahl
    """
    basket = data.groupby("order_id")["product_name"].apply(list)
    pairs = Counter()
    for items in basket:
        unique_items = sorted(set(items))
        for pair in combinations(unique_items, 2):
            pairs[pair] += 1
    return pairs


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

def build_confidence_rules(
    pairs: Counter,
    data: pd.DataFrame,
    min_count: int = 10,
) -> list[tuple]:
    """
    Berechnet Confidence-Regeln für alle Produktpaare.

    P(B|A) = support(A∩B) / support(A)

    Args:
        pairs:      Counter aus build_pairs()
        data:       gemergter DataFrame
        min_count:  Mindestanzahl gemeinsamer Bestellungen (filtert seltene Paare)

    Returns:
        Liste von Tuples: (A, B, confidence)
    """
    product_counts = Counter(data["product_name"])
    total_orders = data["order_id"].nunique()
    confidence_rules = []

    for (A, B), count in pairs.items():
        if count < min_count:
            continue

        support_AB = count / total_orders
        support_A  = product_counts[A] / total_orders
        support_B  = product_counts[B] / total_orders

        conf_A_to_B = support_AB / support_A  # P(B|A)
        conf_B_to_A = support_AB / support_B  # P(A|B)

        confidence_rules.append((A, B, conf_A_to_B))
        confidence_rules.append((B, A, conf_B_to_A))

    return confidence_rules


# ---------------------------------------------------------------------------
# Lift
# ---------------------------------------------------------------------------

def build_lift_rules(
    pairs: Counter,
    data: pd.DataFrame,
    min_count: int = 100,
) -> list[tuple]:
    """
    Berechnet Lift-Werte für alle Produktpaare.

    Lift > 1 → Produkte werden häufiger zusammen gekauft als zufällig erwartet
    Lift = 1 → Zufall
    Lift < 1 → Produkte werden eher nicht zusammen gekauft

    Args:
        pairs:      Counter aus build_pairs()
        data:       gemergter DataFrame
        min_count:  Mindestanzahl gemeinsamer Bestellungen

    Returns:
        Liste von Tuples: (A, B, lift)
    """
    product_counts = Counter(data["product_name"])
    total_orders = data["order_id"].nunique()
    lift_rules = []

    for (A, B), count in pairs.items():
        if count < min_count:
            continue

        support_AB = count / total_orders
        support_A  = product_counts[A] / total_orders
        support_B  = product_counts[B] / total_orders

        lift = support_AB / (support_A * support_B)
        lift_rules.append((A, B, lift))

    return lift_rules


# ---------------------------------------------------------------------------
# Graph aufbauen
# ---------------------------------------------------------------------------

def build_lift_graph(
    pairs: Counter,
    data: pd.DataFrame,
    ranking: pd.DataFrame,
    top_n: int = 300,
    min_count: int = 50,
    min_lift: float = 2.0,
) -> nx.Graph:
    """
    Baut einen gewichteten NetworkX-Graph basierend auf Lift-Werten.

    Args:
        pairs:      Counter aus build_pairs()
        data:       gemergter DataFrame
        ranking:    DataFrame aus build_ranking()
        top_n:      Nur die Top-N Produkte nach Häufigkeit berücksichtigen
        min_count:  Mindestanzahl gemeinsamer Bestellungen für eine Kante
        min_lift:   Mindest-Lift für eine Kante

    Returns:
        nx.Graph mit Edge-Attribut 'weight' (Lift) und Node-Attribut 'share'
    """
    product_counts = Counter(data["product_name"])
    total_orders = data["order_id"].nunique()
    top_products = set(ranking.head(top_n)["Produkt"])
    share_dict = dict(zip(ranking["Produkt"], ranking["Anzahl"]))

    G = nx.Graph()

    for (a, b), count in pairs.items():
        if a not in top_products or b not in top_products:
            continue
        if count < min_count:
            continue

        support_ab = count / total_orders
        support_a  = product_counts[a] / total_orders
        support_b  = product_counts[b] / total_orders
        lift = support_ab / (support_a * support_b)

        if lift < min_lift:
            continue

        G.add_edge(a, b, weight=lift)
        G.nodes[a]["share"] = share_dict.get(a, 0)
        G.nodes[b]["share"] = share_dict.get(b, 0)

    return G


# ---------------------------------------------------------------------------
# Layout / Koordinaten
# ---------------------------------------------------------------------------

def get_coords(graph: nx.Graph, pos: dict) -> tuple:
    """
    Extrahiert X/Y/Z-Koordinaten für Nodes und Edges aus einem spring_layout.

    Returns:
        (x_nodes, y_nodes, z_nodes, x_edges, y_edges, z_edges)
    """
    x_nodes, y_nodes, z_nodes = [], [], []
    for node in graph.nodes():
        x, y, z = pos[node]
        x_nodes.append(x)
        y_nodes.append(y)
        z_nodes.append(z)

    x_edges, y_edges, z_edges = [], [], []
    for edge in graph.edges():
        x0, y0, z0 = pos[edge[0]]
        x1, y1, z1 = pos[edge[1]]
        x_edges += [x0, x1, None]
        y_edges += [y0, y1, None]
        z_edges += [z0, z1, None]

    return x_nodes, y_nodes, z_nodes, x_edges, y_edges, z_edges


# ---------------------------------------------------------------------------
# Plotly Visualisierung
# ---------------------------------------------------------------------------

def build_plot(
    graph: nx.Graph,
    pos: dict,
    ranking: pd.DataFrame,
    communities: list | None = None,
) -> go.Figure:
    """
    Erstellt eine interaktive 3D-Plotly-Visualisierung des Graphen.

    Args:
        graph:        nx.Graph aus build_lift_graph()
        pos:          Layout-Dict aus nx.spring_layout()
        ranking:      DataFrame aus build_ranking() (für Markergrösse)
        communities:  Liste von frozensets aus detect_communities() – optional.
                      Falls angegeben, wird jeder Cluster in einer eigenen Farbe
                      dargestellt und in der Legende aufgeführt.

    Returns:
        plotly Figure

    Beispiel:
        communities = detect_communities(G)
        fig = build_plot(G, pos, ranking, communities=communities)
        fig.show()
    """
    share_dict = dict(zip(ranking["Produkt"], ranking["Share in %"]))
    nodes = list(graph.nodes())
    degrees = dict(graph.degree())
    fig = go.Figure()

    if communities:
        # Pro Community einen eigenen Trace → eigene Farbe + Legendeneintrag
        for i, community in enumerate(communities):
            members = [n for n in nodes if n in community]
            if not members:
                continue

            x_c, y_c, z_c, sizes_c, deg_c = [], [], [], [], []
            for node in members:
                x, y, z = pos[node]
                x_c.append(x)
                y_c.append(y)
                z_c.append(z)
                sizes_c.append(max(share_dict.get(node, 0.1) * 10, 3))
                deg_c.append(degrees[node])

            fig.add_trace(go.Scatter3d(
                x=x_c, y=y_c, z=z_c,
                mode="markers",
                text=members,
                customdata=deg_c,
                hovertemplate="Produkt: %{text}<br>Verbindungen: %{customdata:.0f}<extra></extra>",
                marker=dict(size=sizes_c),
                name=f"Cluster {i}",
            ))
    else:
        # Keine Communities → alle Knoten einheitlich
        x_nodes, y_nodes, z_nodes, *_ = get_coords(graph, pos)
        degree_values = [degrees[n] for n in nodes]
        node_sizes = [max(share_dict.get(n, 0.1) * 10, 3) for n in nodes]

        fig.add_trace(go.Scatter3d(
            x=x_nodes, y=y_nodes, z=z_nodes,
            mode="markers",
            text=nodes,
            customdata=degree_values,
            hovertemplate="Produkt: %{text}<br>Verbindungen: %{customdata:.0f}<extra></extra>",
            marker=dict(size=node_sizes),
            name="Produkte",
        ))

    fig.update_layout(
        showlegend=bool(communities),
        scene=dict(
            xaxis=dict(showticklabels=False, title=""),
            yaxis=dict(showticklabels=False, title=""),
            zaxis=dict(showticklabels=False, title=""),
        ),
        margin=dict(l=0, r=0, t=0, b=0),
    )

    return fig


# ---------------------------------------------------------------------------
# Community Detection
# ---------------------------------------------------------------------------

def detect_communities(graph: nx.Graph) -> list:
    """
    Erkennt Produktgruppen (Communities) im Graph via greedy modularity.

    Returns:
        Liste von frozensets mit Produktnamen
    """
    return list(greedy_modularity_communities(graph, weight="weight"))


def communities_to_dataframe(communities: list) -> pd.DataFrame:
    """
    Konvertiert die Community-Liste in einen lesbaren DataFrame.

    Returns:
        DataFrame mit Spalten: Community, Produkt
    """
    rows = []
    for i, community in enumerate(communities):
        for product in sorted(community):
            rows.append({"Community": i, "Produkt": product})
    return pd.DataFrame(rows)

def save_processed(
    data: pd.DataFrame,
    ranking: pd.DataFrame,
    pairs: Counter,
    out_dir: str = "../data",
) -> None:
    import pickle, os
    os.makedirs(out_dir, exist_ok=True)
    with open(f"{out_dir}/data.pkl", "wb") as f:
        pickle.dump(data, f)
    with open(f"{out_dir}/ranking.pkl", "wb") as f:
        pickle.dump(ranking, f)
    with open(f"{out_dir}/pairs.pkl", "wb") as f:
        pickle.dump(pairs, f)
    print(f"Gespeichert in {out_dir}/")


def load_processed(
    out_dir: str = "../data",
) -> tuple:
    import pickle
    with open(f"{out_dir}/data.pkl", "rb") as f:
        data = pickle.load(f)
    with open(f"{out_dir}/ranking.pkl", "rb") as f:
        ranking = pickle.load(f)
    with open(f"{out_dir}/pairs.pkl", "rb") as f:
        pairs = pickle.load(f)
    return data, ranking, pairs
