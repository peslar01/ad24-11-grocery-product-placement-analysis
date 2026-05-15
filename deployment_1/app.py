"""
Instacart Product Placement Dashboard — deployment_1 (updated version)
======================================================================

This is a parallel copy of ../deployment/app.py.  Every page is identical
EXCEPT  "Product Development → Products Bought Together", which has been
rebuilt as an **aisle-level** market basket analysis.

What changed and why
--------------------
The original co-purchase view ran on individual products. The 300-500 most
purchased products on Instacart are almost all fresh produce, while pasta,
snacks etc. are split across hundreds of separate SKUs — so they never form
their own clusters.  Grouping every product into its aisle (134 aisles)
removes that fragmentation and makes the co-purchase structure interpretable.

This version also no longer needs the pre-computed .pkl files — the aisle
analysis is light enough to compute directly from the CSVs and cache.

Run it:
    uv run streamlit run deployment_1/app.py
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import seaborn as sns
import matplotlib.pyplot as plt
import streamlit as st

from defs_aisle_network import (
    compute_aisle_pairs, build_edges, giant_component,
    detect_communities, spring_layout, build_figure, cluster_summary,
)

st.set_page_config(
    page_title="Instacart EDA — aisle-level",
    page_icon="🛒",
    layout="wide",
)

# data lives at the project root: PODSV_Project/data
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

CSV_FILES = [
    "orders.csv", "products.csv", "aisles.csv",
    "departments.csv", "order_products__prior.csv",
]


@st.cache_data(show_spinner="Loading data …")
def load_csv():
    orders = pd.read_csv(DATA_DIR / "orders.csv")
    products = pd.read_csv(DATA_DIR / "products.csv")
    aisles = pd.read_csv(DATA_DIR / "aisles.csv")
    departments = pd.read_csv(DATA_DIR / "departments.csv")
    order_products = pd.read_csv(DATA_DIR / "order_products__prior.csv")
    products_full = products.merge(aisles, on="aisle_id").merge(departments, on="department_id")
    return orders, products, products_full, order_products


# ── Aisle-level market basket analysis (cached) ───────────────────────────────
@st.cache_data(show_spinner="Counting aisle co-purchases — one-time, ~30–60 s …")
def load_aisle_pairs():
    """Heavy step: count how often each pair of aisles is bought together."""
    return compute_aisle_pairs(str(DATA_DIR))


@st.cache_data(show_spinner="Building the aisle network …")
def build_aisle_network(min_count: int, min_lift: float):
    pairs, count_a, n_orders, aid2name = load_aisle_pairs()
    edges = build_edges(pairs, count_a, n_orders, aid2name,
                        min_count=min_count, min_lift=min_lift)
    giant, edges = giant_component(edges)
    nodes = sorted(giant)
    node_comm = detect_communities(nodes, edges)
    pos = spring_layout(nodes, edges, node_comm)
    fig = build_figure(nodes, edges, node_comm, pos, count_a, aid2name)
    summary = cluster_summary(nodes, node_comm, count_a, aid2name)
    return fig, summary, len(nodes), len(edges)


# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("Instacart Product Placement Analysis")
st.sidebar.caption("deployment_1 · aisle-level co-purchase update")

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

# ── Guard: missing CSV files ──────────────────────────────────────────────────
missing_csv = [f for f in CSV_FILES if not (DATA_DIR / f).exists()]
if missing_csv:
    st.error(
        f"Missing CSV files in `{DATA_DIR}`: {', '.join(missing_csv)}\n\n"
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

        > **deployment_1 note —** this is the updated build: the
        *Products Bought Together* page now runs an **aisle-level** market
        basket analysis instead of a product-level one.
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
            color_continuous_scale="Greens",
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
        st.title("Products Bought Together — Aisle-Level Market Basket Analysis")

        st.markdown(
            """
            **What changed in this version.** The original analysis ran on
            individual products. But the 300–500 most-purchased products are
            almost all fresh produce, while categories like *pasta* or *snacks*
            are split across hundreds of separate SKUs — so they could never
            form their own clusters.

            This page groups every product into its **aisle** (134 aisles).
            Each pasta SKU collapses into one strong *dry pasta* node, each
            chip SKU into *chips pretzels*, and the co-purchase structure
            finally becomes interpretable.
            """
        )

        st.markdown(
            "Nodes = aisles · Edges = aisles frequently bought together · "
            "Node size = how many orders contain that aisle · Colour = cluster"
        )

        with st.expander("How to read this chart — Guide"):
            st.markdown(
                """
### What is this?

For every pair of aisles, we count how many orders contain **both**, then
compute the **lift** — how much more often they are bought together than
random chance would predict.

| Lift value | Meaning |
|---|---|
| **= 1.0** | No association — co-occurrence is pure coincidence |
| **> 1.0** | Positive association — bought together more than expected |
| **> 1.5** | Strong association — a reliable co-purchase pattern |

Aisles connected by these lift edges are then grouped into **clusters**
(communities) using weighted greedy-modularity detection. Each cluster is a
natural "shopping basket".

### Sidebar parameters

**Minimum co-occurrence count** — how many orders two aisles must share
before an edge is drawn. Filters out rare, accidental pairings.

**Minimum lift** — the lowest lift required to draw an edge. Higher values
keep only the strongest associations.

### How to use the results

- **Cross-sell**: recommend aisles within the same cluster
- **Bundling**: promote products from tightly linked aisles together
- **Layout**: place cluster members in the same app section / shelf zone
                """
            )

        with st.sidebar:
            st.divider()
            st.subheader("Parameters")
            min_count = st.slider("Minimum co-occurrence count",
                                  500, 20000, 2000, step=500)
            min_lift  = st.slider("Minimum lift", 1.0, 3.0, 1.3, step=0.1)

        fig, summary, n_nodes, n_edges = build_aisle_network(min_count, min_lift)

        col1, col2, col3 = st.columns(3)
        col1.metric("Aisles (nodes)", n_nodes)
        col2.metric("Co-purchase links", n_edges)
        col3.metric("Clusters found", len(summary))

        st.plotly_chart(fig, width='stretch')

        st.subheader("The clusters")
        for c in summary:
            st.markdown(
                f"<span style='display:inline-block;width:12px;height:12px;"
                f"border-radius:50%;background:{c['colour']};margin-right:8px'></span>"
                f"**Cluster {c['cluster']}** · {c['size']} aisles",
                unsafe_allow_html=True,
            )
            st.caption(", ".join(c["aisles"]))

        st.info(
            "Grouped by aisle, baskets split by **shopping mission**: a large "
            "*cooking basket* (fresh produce, dairy, meat — plus pasta, sauce, "
            "oils and spices), a *convenience & household run* (snacks, drinks, "
            "frozen meals, cleaning and personal care), a remarkably tight "
            "*drinks run* (beer, wine, spirits), and a small *health & bulk* "
            "basket. Note that pasta does **not** form its own cluster — it "
            "groups with the ingredients it is cooked with — and snacks group "
            "with the convenience run, not with pasta."
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
            color_continuous_scale="Greens",
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

        dept_sales = (
            order_products
            .merge(products_full[["product_id", "department_id"]], on="product_id")
            .groupby("department_id")["product_id"]
            .count()
            .reset_index(name="purchase_count")
            .sort_values("purchase_count", ascending=False)
        )
        top_dept_ids = set(dept_sales.head(top_n_depts)["department_id"])

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
                color_continuous_scale="Greens",
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
            "Darker cells indicate higher order volumes for that day-hour combination."
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
            cmap="YlGn",
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
