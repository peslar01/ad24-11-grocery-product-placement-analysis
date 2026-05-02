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

section = st.sidebar.radio(
    "Section",
    ["KPI Overview", "Product Development", "Customer Retention"],
)

sub_page = None

if section == "Product Development":
    st.sidebar.divider()
    sub_page = st.sidebar.radio(
        "Product Development",
        ["Top Sellers", "Department Sales", "Products Bought Together"],
    )
elif section == "Customer Retention":
    st.sidebar.divider()
    sub_page = st.sidebar.radio(
        "Customer Retention",
        ["Reorder Rate", "Hidden Gems", "Shopping Time Heatmap"],
    )

# ── Guard: missing CSV files ───────────────────────────────────────────────
missing_csv = [f for f in CSV_FILES if not (DATA_DIR / f).exists()]
network_active = (section == "Product Development" and sub_page == "Products Bought Together")

if missing_csv and not network_active:
    st.error(
        f"Missing CSV files in `data/`: {', '.join(missing_csv)}\n\n"
        "Please run the **data_acquisition** notebook first."
    )
    st.stop()

# ── Pages ─────────────────────────────────────────────────────────────────────

if section == "KPI Overview":
    st.title("Instacart Market Basket — Dashboard Overview")

    st.markdown(
        """
        This dashboard explores the **Instacart Online Grocery** dataset,
        covering over 3 million grocery orders placed by more than 200,000 customers.
        Use the sidebar to navigate between the **Product Development** and
        **Customer Retention** analysis sections.
        """
    )

    orders, products, products_full, order_products = load_csv()

    total_orders     = orders["order_id"].nunique()
    unique_products  = products["product_id"].nunique()
    unique_customers = orders["user_id"].nunique()
    overall_reorder  = order_products["reordered"].mean()
    peak_hour        = int(orders["order_hour_of_day"].mode()[0])

    dept_sales = (
        order_products
        .merge(products_full[["product_id", "department"]], on="product_id")
        .groupby("department")["product_id"]
        .count()
    )
    top_department = dept_sales.idxmax()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Orders",      f"{total_orders:,}")
    col2.metric("Unique Products",   f"{unique_products:,}")
    col3.metric("Unique Customers",  f"{unique_customers:,}")

    col4, col5, col6 = st.columns(3)
    col4.metric("Overall Reorder Rate", f"{overall_reorder:.1%}")
    col5.metric("Top Department",        top_department)
    col6.metric("Peak Shopping Hour",    f"{peak_hour}:00")

    st.info(
        "The dataset spans over 200,000 customers and more than 49,000 unique products. "
        "Produce dominates sales, and most shopping happens on Sunday and Monday mornings. "
        "An overall reorder rate above 58% signals a highly habitual customer base — "
        "ideal conditions for loyalty-driven product strategies."
    )


elif section == "Product Development":

    if sub_page == "Top Sellers":
        st.title("Top Products by Number of Purchases")
        st.markdown(
            "Shows the most frequently purchased individual products across all orders. "
            "Use the slider to control how many products are displayed."
        )

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

    elif sub_page == "Department Sales":
        st.title("Sales by Department")
        st.markdown(
            "Compares total purchase volume across all product departments. "
            "This reveals which categories drive the most revenue and customer engagement."
        )

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

    elif sub_page == "Products Bought Together":
        st.title("Products Bought Together (Market Basket Analysis)")
        st.markdown(
            "Visualizes which products are frequently purchased in the same order. "
            "Nodes represent products, edges indicate strong co-purchase associations (lift). "
            "Color-coded clusters reveal natural product groups."
        )

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

        with st.expander("How to read this chart — Guide"):
            st.markdown(
                """
### What is Market Basket Analysis?

Market Basket Analysis finds products that customers tend to buy **in the same order**.
It answers: *"If a customer buys product A, how likely are they to also buy product B?"*

---

### Reading the Graph

| Element | What it means |
|---|---|
| **Node (sphere)** | A single product |
| **Node size** | How often that product is purchased overall — bigger = more popular |
| **Node colour** | The community (cluster) the product belongs to |
| **Edge (line)** | The two products are frequently bought together |
| **Edge thickness** | Strength of the association (lift value) |

---

### The Key Metric: Lift

**Lift** measures how much more often two products are bought together compared to what you'd expect by chance.

| Lift value | Meaning |
|---|---|
| **= 1.0** | No association — products are bought together by coincidence only |
| **> 1.0** | Positive association — customers buy them together more than expected |
| **> 2.0** | Strong association — a good cross-sell candidate |
| **> 3.0** | Very strong — nearly always purchased together |

> Example: Lift of 3.0 for *Limes + Avocado* means customers buy them together **3× more often** than chance would predict.

---

### Sidebar Parameters

**Top-N Products** — how many of the most popular products to include in the graph.
A higher number shows more connections but makes the graph slower and harder to read.
Start with 150–300 for a clear overview.

**Minimum pair count** — how many times two products must have been bought together to draw an edge.
Raise this to filter out weak or accidental associations and focus on reliable patterns.

**Minimum lift** — the lowest lift value required to draw an edge.
Values below 1.5 produce a very dense graph; values above 3.0 show only the strongest links.

---

### How to use the results

- **Cross-sell**: Products connected by a strong edge are good candidates to recommend together ("Customers also bought…")
- **Bundling**: A tight cluster of products can be packaged as a promotional bundle
- **App placement**: Products in the same community should be grouped together in the same app category or shown in the same search results
- **Promotions**: Discounting one product in a pair with high lift will likely increase sales of its partner
                """
            )

        with st.sidebar:
            st.divider()
            st.subheader("Parameters")
            top_n     = st.slider("Top-N Products",     50,  500, 300, step=50)
            min_count = st.slider("Minimum pair count", 10,  200,  50, step=10)
            min_lift  = st.slider("Minimum lift",       1.0, 5.0,  2.0, step=0.5)

        fig, n_nodes, n_edges = build_network_figure(top_n, min_count, min_lift)

        col1, col2 = st.columns(2)
        col1.metric("Nodes (Products)", n_nodes)
        col2.metric("Edges (Connections)", n_edges)

        st.plotly_chart(fig, width='stretch', height=700)

        st.info(
            "Products are connected when they are frequently purchased together "
            "and their lift exceeds the minimum threshold. "
            "Clusters reveal natural product groups — useful for cross-sell recommendations, "
            "bundle promotions, and optimising store shelf placement."
        )


elif section == "Customer Retention":

    if sub_page == "Reorder Rate":
        st.title("Top Products by Reorder Rate")
        st.markdown(
            "The reorder rate measures how often customers buy a product again after their first purchase. "
            "A high reorder rate indicates a loyal, habitual customer base for that product."
        )

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

    elif sub_page == "Hidden Gems":
        st.title("Hidden Gems — Niche Products with Loyal Customers")
        st.markdown(
            "Hidden Gems are products that belong to smaller, less dominant departments "
            "but still achieve exceptionally high reorder rates. "
            "These products have a small but very loyal customer base."
        )

        orders, products, products_full, order_products = load_csv()

        top_n_depts   = st.slider("Exclude top N departments by sales", 1, 10, 5)
        min_purchases = st.slider("Minimum number of purchases", 100, 2000, 500, step=100)
        n_products    = st.slider("Number of products to show", 5, 40, 20)

        # Identify top-N departments by total purchase volume
        dept_sales = (
            order_products
            .merge(products_full[["product_id", "department_id"]], on="product_id")
            .groupby("department_id")["product_id"]
            .count()
            .reset_index(name="purchase_count")
            .sort_values("purchase_count", ascending=False)
        )
        top_dept_ids = set(dept_sales.head(top_n_depts)["department_id"])

        # Products NOT in the top departments
        nontop_product_ids = set(
            products_full.loc[
                ~products_full["department_id"].isin(top_dept_ids), "product_id"
            ]
        )

        nontop_orders = order_products[order_products["product_id"].isin(nontop_product_ids)]

        purchase_counts = (
            nontop_orders.groupby("product_id")["product_id"]
            .count()
            .rename("purchase_count")
        )
        eligible = purchase_counts[purchase_counts >= min_purchases].index

        reorder_rates = (
            nontop_orders[nontop_orders["product_id"].isin(eligible)]
            .groupby("product_id")["reordered"]
            .mean()
            .reset_index()
            .rename(columns={"reordered": "reorder_rate"})
        )

        hidden_gems = (
            reorder_rates
            .merge(products[["product_id", "product_name"]], on="product_id")
            .sort_values("reorder_rate", ascending=False)
            .head(n_products)
            .sort_values("reorder_rate")
        )

        if hidden_gems.empty:
            st.warning(
                "No products found with the current filters. "
                "Try lowering the minimum purchase threshold or increasing the number of excluded departments."
            )
        else:
            fig = px.bar(
                hidden_gems,
                x="reorder_rate",
                y="product_name",
                orientation="h",
                labels={"reorder_rate": "Reorder Rate", "product_name": ""},
                color="reorder_rate",
                color_continuous_scale="Blues",
                range_x=[0, 1],
            )
            fig.update_layout(
                coloraxis_showscale=False,
                height=max(400, n_products * 22),
            )
            st.plotly_chart(fig, width='stretch')

        st.info(
            "These niche products are purchased less often overall, but the customers who do buy them "
            "come back repeatedly. They are strong candidates for **targeted promotions**, "
            "category-specific newsletters, or **subscription offers** to deepen retention "
            "beyond the mainstream produce and dairy categories."
        )

    elif sub_page == "Shopping Time Heatmap":
        st.title("Order Frequency by Day and Time")
        st.markdown(
            "Shows when customers are most likely to place orders throughout the week. "
            "Brighter cells indicate higher order volumes for that day-hour combination."
        )

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
        st.pyplot(fig)

        st.info(
            "Most orders are placed **on Sundays and Mondays between 9:00 and 15:00**. "
            "Customers typically plan their weekly groceries at the start of the week. "
            "Activity is very low before 6 AM and after 10 PM on all days. "
            "This pattern suggests that promotional pushes on Saturday evenings could "
            "capture early weekend planners before the Sunday peak."
        )
