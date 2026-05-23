"""KPI Overview — landing page with headline metrics and a top-5 dept chart."""

import plotly.express as px
import streamlit as st

from data_loaders import load_csv


def render():
    st.title("Instacart Market Basket — Dashboard Overview")

    st.markdown(
        "This dashboard explores the **Instacart Online Grocery** dataset, "
        "covering over 3 million grocery orders placed by more than 200'000 customers. "
        "Start with **Product Development** to see what sells, then continue with "
        "**Customer Retention** to understand who keeps coming back."
    )

    orders, products, products_full, order_products = load_csv()

    # ── Scale ────────────────────────────────────────────────────────────────
    total_orders     = orders["order_id"].nunique()
    unique_products  = products["product_id"].nunique()
    unique_customers = orders["user_id"].nunique()

    # ── Behaviour ────────────────────────────────────────────────────────────
    overall_reorder         = order_products["reordered"].mean()
    avg_orders_per_customer = total_orders / unique_customers
    avg_basket_size         = order_products.groupby("order_id").size().mean()

    # ── Preferences ──────────────────────────────────────────────────────────
    dept_purchases = (
        order_products
        .merge(products_full[["product_id", "department"]], on="product_id")
        .groupby("department")
        .size()
    )
    dept_share     = dept_purchases / dept_purchases.sum()
    top_department = dept_share.idxmax()
    top_dept_share = dept_share.max()

    peak_dh   = orders.groupby(["order_dow", "order_hour_of_day"]).size().idxmax()
    day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    peak_label = f"{day_names[peak_dh[0]]}, {peak_dh[1]:02d}:00"

    # ── Metric grid ──────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Orders",     f"{total_orders:,}")
    col2.metric("Unique Products",  f"{unique_products:,}")
    col3.metric("Unique Customers", f"{unique_customers:,}")

    col4, col5, col6 = st.columns(3)
    col4.metric("Overall Reorder Rate", f"{overall_reorder:.1%}")
    col5.metric("Avg Orders / Customer", f"{avg_orders_per_customer:.1f}")
    col6.metric("Avg Products / Order",  f"{avg_basket_size:.1f}")

    col7, col8 = st.columns(2)
    col7.metric(
        "Top Department",
        f"{top_department.title()} ({top_dept_share:.0%})",
    )
    col8.metric("Peak Shopping Time", peak_label)

    # ── Mini chart: top 5 departments by share ───────────────────────────────
    st.divider()
    st.subheader("Sales share — top 5 departments")
    top5 = (
        dept_share.sort_values(ascending=False)
        .head(5)
        .reset_index()
    )
    top5.columns = ["department", "share"]
    top5["share_pct"] = (top5["share"] * 100).round(1)
    top5 = top5.sort_values("share_pct")

    fig = px.bar(
        top5,
        x="share_pct",
        y="department",
        orientation="h",
        text="share_pct",
        labels={"share_pct": "Share of all purchases (%)", "department": ""},
        color="share_pct",
        color_continuous_scale="Oranges",
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig.update_layout(
        coloraxis_showscale=False,
        height=290,
        margin=dict(t=10, l=10, r=40, b=10),
        xaxis=dict(range=[0, top5["share_pct"].max() * 1.15]),
    )
    st.plotly_chart(fig, width='stretch')

    st.info(
        "The dataset spans over 200'000 customers and more than 49'000 unique products. "
        "**Produce** alone accounts for almost a third of all purchases, and most shopping "
        "happens on Sunday and Monday mornings. With an average of "
        f"**{avg_orders_per_customer:.0f} orders per customer** and a reorder rate of "
        f"**{overall_reorder:.0%}**, the platform shows a highly habitual customer base, "
        "ideal conditions for loyalty-driven product strategies."
    )
