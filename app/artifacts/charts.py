"""Matplotlib chart generators for business analysis reports."""

from pathlib import Path
from typing import List, Dict, Any, Optional
import matplotlib
matplotlib.use("Agg")  # Headless backend for server environment
import matplotlib.pyplot as plt

from app.config import settings


def generate_sales_trend_chart(trend_data: List[Dict[str, Any]], filename: str = "sales_trend.png") -> str:
    """Generate daily sales trend line + bar chart."""
    output_path = str(settings.ensure_artifacts_dir() / filename)

    dates = [item.get("day_name", item.get("date", "")) for item in trend_data]
    sales = [item.get("sales", 0.0) for item in trend_data]

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    bars = ax.bar(dates, sales, color="#3182CE", alpha=0.85, width=0.5, label="Daily Sales (₹)")
    ax.plot(dates, sales, color="#2B6CB0", marker="o", linewidth=2.2, markersize=6)

    # Add data labels
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax.annotate(
                f"₹{height:,.0f}",
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8,
                fontweight="bold",
            )

    ax.set_title("Daily Sales Trend (Last 7 Days)", fontsize=13, fontweight="bold", pad=12, color="#1A202C")
    ax.set_ylabel("Sales Amount (₹)", fontsize=10, fontweight="medium")
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close(fig)
    return output_path


def generate_top_products_chart(products_data: List[Dict[str, Any]], filename: str = "top_products.png") -> str:
    """Generate horizontal bar chart for top products."""
    output_path = str(settings.ensure_artifacts_dir() / filename)

    names = [p.get("name", "") for p in reversed(products_data)] or ["No Data"]
    quantities = [p.get("quantity_sold", 0.0) for p in reversed(products_data)] or [0]

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    bars = ax.barh(names, quantities, color="#38A169", alpha=0.85, height=0.55)

    for bar in bars:
        width = bar.get_width()
        if width > 0:
            ax.annotate(
                f"{width:g}",
                xy=(width, bar.get_y() + bar.get_height() / 2),
                xytext=(4, 0),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=8,
                fontweight="bold",
            )

    ax.set_title("Top Selling Products (Quantity)", fontsize=13, fontweight="bold", pad=12, color="#1A202C")
    ax.set_xlabel("Units Sold", fontsize=10)
    ax.grid(axis="x", linestyle="--", alpha=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close(fig)
    return output_path


def generate_low_stock_chart(low_stock_items: List[Dict[str, Any]], filename: str = "low_stock.png") -> str:
    """Generate comparison bar chart of current stock vs reorder level."""
    output_path = str(settings.ensure_artifacts_dir() / filename)

    names = [item.get("name", "")[:16] for item in low_stock_items[:6]] or ["Healthy Stock"]
    stocks = [item.get("current_stock", 0.0) for item in low_stock_items[:6]] or [0]
    reorders = [item.get("reorder_level", 0.0) for item in low_stock_items[:6]] or [0]

    import numpy as np
    x = np.arange(len(names))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    ax.bar(x - width/2, stocks, width, label="Current Stock", color="#E53E3E", alpha=0.85)
    ax.bar(x + width/2, reorders, width, label="Reorder Level", color="#718096", alpha=0.6)

    ax.set_title("Low Stock Warning (Current vs Threshold)", fontsize=13, fontweight="bold", pad=12, color="#1A202C")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=20, ha="right", fontsize=9)
    ax.set_ylabel("Quantity", fontsize=10)
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close(fig)
    return output_path
