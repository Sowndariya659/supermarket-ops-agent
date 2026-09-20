"""Analytics and business metrics aggregation service."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.database.models import Bill, BillItem, Product, Inventory


class AnalyticsService:
    def __init__(self, session: Session):
        self.session = session

    def get_sales_summary(self, period: str = "today") -> Dict[str, Any]:
        """Aggregate sales metrics for a specified period ('today', 'yesterday', 'week', 'month', 'all')."""
        now = datetime.utcnow()
        if period == "today":
            start_time = datetime(now.year, now.month, now.day, 0, 0, 0)
        elif period == "yesterday":
            yesterday = now - timedelta(days=1)
            start_time = datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0)
            end_time = datetime(now.year, now.month, now.day, 0, 0, 0)
        elif period == "week":
            start_time = now - timedelta(days=7)
        elif period == "month":
            start_time = now - timedelta(days=30)
        else:
            start_time = datetime(2000, 1, 1)

        query = self.session.query(Bill).filter(
            Bill.status == "FINALIZED",
            Bill.finalized_at >= start_time,
        )
        if period == "yesterday":
            query = query.filter(Bill.finalized_at < end_time)

        bills = query.all()

        total_sales = Decimal("0.00")
        total_subtotal = Decimal("0.00")
        total_cgst = Decimal("0.00")
        total_sgst = Decimal("0.00")
        total_tax = Decimal("0.00")
        payment_modes: Dict[str, float] = {}

        for b in bills:
            total_sales += b.grand_total
            total_subtotal += b.subtotal
            total_cgst += b.cgst
            total_sgst += b.sgst
            total_tax += b.total_tax
            pm = b.payment_mode or "UNKNOWN"
            payment_modes[pm] = payment_modes.get(pm, 0.0) + float(b.grand_total)

        count = len(bills)
        avg_ticket = float(total_sales / count) if count > 0 else 0.0

        return {
            "period": period,
            "bill_count": count,
            "total_sales": float(total_sales),
            "total_subtotal": float(total_subtotal),
            "total_cgst": float(total_cgst),
            "total_sgst": float(total_sgst),
            "total_tax": float(total_tax),
            "average_ticket_size": avg_ticket,
            "payment_modes_breakdown": payment_modes,
        }

    def get_top_selling_products(self, days: int = 7, limit: int = 5) -> List[Dict[str, Any]]:
        """Find the top selling products by quantity and revenue over recent days."""
        start_date = datetime.utcnow() - timedelta(days=days)
        results = (
            self.session.query(
                Product.id,
                Product.name,
                Product.unit,
                func.sum(BillItem.quantity).label("total_qty"),
                func.sum(BillItem.total).label("total_revenue"),
            )
            .join(BillItem, Product.id == BillItem.product_id)
            .join(Bill, BillItem.bill_id == Bill.id)
            .filter(Bill.status == "FINALIZED", Bill.finalized_at >= start_date)
            .group_by(Product.id, Product.name, Product.unit)
            .order_by(desc("total_qty"))
            .limit(limit)
            .all()
        )

        return [
            {
                "product_id": r[0],
                "name": r[1],
                "unit": r[2],
                "quantity_sold": float(r[3] or 0),
                "revenue": float(r[4] or 0),
            }
            for r in results
        ]

    def get_daily_sales_trend(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get daily sales totals for past N days."""
        trend = []
        now = datetime.utcnow()
        for i in range(days - 1, -1, -1):
            day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            sales = (
                self.session.query(func.coalesce(func.sum(Bill.grand_total), Decimal("0.00")))
                .filter(
                    Bill.status == "FINALIZED",
                    Bill.finalized_at >= day_start,
                    Bill.finalized_at < day_end,
                )
                .scalar()
            )
            bill_count = (
                self.session.query(func.count(Bill.id))
                .filter(
                    Bill.status == "FINALIZED",
                    Bill.finalized_at >= day_start,
                    Bill.finalized_at < day_end,
                )
                .scalar()
            )
            trend.append(
                {
                    "date": day_start.strftime("%Y-%m-%d"),
                    "day_name": day_start.strftime("%a"),
                    "sales": float(sales),
                    "bill_count": bill_count,
                }
            )
        return trend
