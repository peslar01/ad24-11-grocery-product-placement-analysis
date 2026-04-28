import pickle
import sys
from pathlib import Path

import networkx as nx
import pandas as pd
import plotly.express as px
import seaborn as sns
import matplotlib.pyplot as plt
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "eda"))
from defs_graph_plot import build_lift_graph, build_plot, detect_communities  # type: ignore

st.set_page_config(
    page_title="Instacart EDA",
    page_icon="🛒",
    layout="wide",
)

DATA_DIR = Path(__file__).parent / "data"

CSV_FILES = [
    "orders.csv", "products.csv", "aisles.csv",
    "departments.csv", "order_products__prior.csv",
]
PKL_FILES = ["data.pkl", "ranking.pkl", "pairs.pkl"]


@st.cache_data(show_spinner="Loading data …")
def load_csv():
    orders = pd.read_csv(DATA_DIR / "orders.csv")
    products = pd.read_csv(DATA_DIR / "products.csv")
    aisles = pd.read_csv(DATA_DIR / "aisles.csv")
    departments = pd.read_csv(DATA_DIR / "departments.csv")
    order_products = pd.read_csv(DATA_DIR / "order_products__prior.csv")
    products_full = products.merge(aisles, on="aisle_id").merge(departments, on="department_id")
    return orders, products, products_full, order_products


@st.cache_data(show_spinner="Loading network data …")
def load_pkl():
    with open(DATA_DIR / "data.pkl", "rb") as f:
        data = pickle.load(f)
    with open(DATA_DIR / "ranking.pkl", "rb") as f:
        ranking = pickle.load(f)
    with open(DATA_DIR / "pairs.pkl", "rb") as f:
        pairs = pickle.load(f)
    return data, ranking, pairs


@st.cache_data(show_spinner="Building network graph (this may take a moment) …")
def build_network_figure(top_n: int, min_count: int, min_lift: float):
    data, ranking, pairs = load_pkl()
    G = build_lift_graph(
        pairs, data, ranking,
        top_n=top_n, min_count=min_count, min_lift=min_lift,
    )
    pos = nx.spring_layout(G, dim=3, k=0.6, iterations=200, seed=42)
    communities = detect_communities(G)
    fig = build_plot(G, pos, ranking, communities=communities)
    return fig, G.number_of_nodes(), G.number_of_edges()


# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("🛒 Instacart EDA")
page = st.sidebar.radio(
    "Visualization",
    ["Top Products", "Sales by Department", "Orders Heatmap", "Reorder Rate", "Product Network"],
)

# ── Guard: missing CSV files ───────────────────────────────────────────────
missing_csv = [f for f in CSV_FILES if not (DATA_DIR / f).exists()]
if missing_csv and page != "Product Network":
    st.error(
        f"Missing CSV files in `data/`: {', '.join(missing_csv)}\n\n"
        "Please run the **data_acquisition** notebook first."
    )
    st.stop()

# ── Pages ─────────────────────────────────────────────────────────────────────

if page == "Top Products":
    st.title("Top Products by Number of Purchases")

    orders, products, products_full, order_products = load_csv()

    n = st.slider("Number of products", 5, 50, 20)

    top_products = (
        order_products.groupby("product_id")["product_id"]
        .count()
        .reset_index(name="count")
        .merge(products[["product_id", "product_name"]], on="product_id")
        .sort_values("count", ascending=False)
        .head(n)
        .sort_values("count")
    )

    fig = px.bar(
        top_products,
        x="count",
        y="product_name",
        orientation="h",
        labels={"count": "Number of Purchases", "product_name": ""},
        color="count",
        color_continuous_scale="Blues",
    )
    fig.update_layout(coloraxis_showscale=False, height=max(400, n * 22))
    st.plotly_chart(fig, width='stretch')

    st.info(
        "Bananas are the most purchased product, followed by Bag of Organic Bananas and "
        "Organic Strawberries. The top products are dominated by fresh fruit and vegetables, "
        "with a strong preference for organic products."
    )


elif page == "Sales by Department":
    st.title("Sales by Department")

    orders, products, products_full, order_products = load_csv()

    dept_counts = (
        order_products.merge(products_full, on="product_id")
        .groupby("department")["product_id"]
        .count()
        .reset_index(name="count")
        .sort_values("count", ascending=True)
    )

    fig = px.bar(
        dept_counts,
        x="count",
        y="department",
        orientation="h",
        labels={"count": "Number of Purchases", "department": ""},
        color="count",
        color_continuous_scale="Oranges",
    )
    fig.update_layout(coloraxis_showscale=False, height=550)
    st.plotly_chart(fig, width='stretch')

    st.info(
        "**Produce** is the most purchased department with ~9M purchases, followed by "
        "**Dairy & Eggs** (~5M). Fresh products clearly dominate. "
        "Bulk, Other, and Alcohol are rarely purchased on this platform."
    )


elif page == "Orders Heatmap":
    st.title("Order Frequency by Day and Time")

    orders, products, products_full, order_products = load_csv()

    day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    heatmap_data = (
        orders.groupby(["order_dow", "order_hour_of_day"])["order_id"]
        .count()
        .unstack()
    )
    heatmap_data.index = day_names

    fig, ax = plt.subplots(figsize=(12, 4))
    sns.heatmap(
        heatmap_data,
        cmap="YlOrRd",
        ax=ax,
        linewidths=0.4,
        linecolor="white",
        cbar_kws={"label": "Number of Orders"},
    )
    ax.set_title("Order Frequency by Day and Hour", fontsize=14, fontweight="bold", pad=12)
    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("")
    plt.tight_layout()
    st.pyplot(fig, width='stretch')

    st.info(
        "Most orders are placed **on Sundays and Mondays between 9:00 and 15:00**. "
        "Customers typically plan their weekly groceries at the start of the week. "
        "Activity is very low before 6 AM and after 10 PM on all days."
    )


elif page == "Reorder Rate":
    st.title("Top Products by Reorder Rate")

    orders, products, products_full, order_products = load_csv()

    min_purchases = st.slider("Minimum number of purchases", 100, 2000, 500, step=100)
    n = st.slider("Number of products", 5, 40, 20)

    reorder_rate = (
        order_products.groupby("product_id")["reordered"]
        .mean()
        .reset_index()
        .rename(columns={"reordered": "reorder_rate"})
    )
    popular = order_products.groupby("product_id")["product_id"].count()
    popular = popular[popular >= min_purchases].index

    top_reorder = (
        reorder_rate[reorder_rate["product_id"].isin(popular)]
        .merge(products[["product_id", "product_name"]], on="product_id")
        .sort_values("reorder_rate", ascending=False)
        .head(n)
        .sort_values("reorder_rate")
    )

    fig = px.bar(
        top_reorder,
        x="reorder_rate",
        y="product_name",
        orientation="h",
        labels={"reorder_rate": "Reorder Rate", "product_name": ""},
        color="reorder_rate",
        color_continuous_scale="Blues",
        range_x=[0, 1],
    )
    fig.update_layout(coloraxis_showscale=False, height=max(400, n * 22))
    st.plotly_chart(fig, width='stretch')

    st.info(
        "Products with a reorder rate above **0.8** are almost exclusively everyday staples "
        "(milk, water, bananas). These are ideal candidates for **subscription models** or "
        "automatic reorder reminders."
    )


elif page == "Product Network":
    st.title("Product Network (Market Basket Analysis)")

    missing_pkl = [f for f in PKL_FILES if not (DATA_DIR / f).exists()]
    if missing_pkl:
        st.error(
            f"Missing files in `data/`: {', '.join(missing_pkl)}\n\n"
            "Please run the **graph_plot** notebook first."
        )
        st.stop()

    st.markdown(
        "Nodes = Products · Edges = frequently bought together · "
        "Node size = purchase frequency · Color = Community"
    )

    with st.sidebar:
        st.divider()
        st.subheader("Parameters")
        top_n = st.slider("Top-N Products", 50, 500, 300, step=50)
        min_count = st.slider("Minimum pair count", 10, 200, 50, step=10)
        min_lift = st.slider("Minimum lift", 1.0, 5.0, 2.0, step=0.5)

    fig, n_nodes, n_edges = build_network_figure(top_n, min_count, min_lift)

    col1, col2 = st.columns(2)
    col1.metric("Nodes (Products)", n_nodes)
    col2.metric("Edges (Connections)", n_edges)

    st.plotly_chart(fig, width='stretch', height=700)
