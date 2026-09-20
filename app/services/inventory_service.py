"""Service handling product catalog, inventory transactions, and stock tracking."""

from decimal import Decimal
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.database.repositories import ProductRepository, InventoryRepository


class InventoryService:
    def __init__(self, session: Session):
        self.session = session
        self.product_repo = ProductRepository(session)
        self.inventory_repo = InventoryRepository(session)

    def search_products(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search products by name, brand, or SKU."""
        products = self.product_repo.search(query, limit=limit)
        return [p.to_dict() for p in products]

    def list_products(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List all available products in store catalog."""
        products = self.product_repo.list_all(limit=limit)
        return [p.to_dict() for p in products]

    def add_product(
        self,
        name: str,
        mrp: float,
        cost_price: float,
        sell_price: float,
        gst_rate: float,
        unit: str = "packet",
        brand: Optional[str] = None,
        is_loose: bool = False,
        hsn_code: str = "1904",
        reorder_level: float = 10.0,
        initial_stock: float = 0.0,
    ) -> Dict[str, Any]:
        """Create a new product in the catalog with initial stock."""
        # Clean sku generation from name and brand
        sku_clean = "".join(c if c.isalnum() else "-" for c in name.upper())[:20]
        sku = f"{sku_clean}-{int(mrp)}"

        # Check existing SKU collision
        existing = self.product_repo.get_by_sku(sku)
        if existing:
            sku = f"{sku}-{int(Decimal(str(initial_stock)))}"

        product = self.product_repo.create(
            name=name,
            sku=sku,
            brand=brand,
            cost_price=Decimal(str(cost_price)),
            sell_price=Decimal(str(sell_price)),
            mrp=Decimal(str(mrp)),
            gst_rate=Decimal(str(gst_rate)),
            unit=unit,
            is_loose=is_loose,
            hsn_code=hsn_code,
            reorder_level=Decimal(str(reorder_level)),
            initial_stock=Decimal(str(initial_stock)),
        )
        self.session.commit()
        return product.to_dict()

    def receive_stock(
        self,
        product_id: int,
        quantity: float,
        cost_price: Optional[float] = None,
        mrp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Record received stock shipment for a product."""
        if quantity <= 0:
            raise ValueError("Received stock quantity must be positive.")

        product = self.product_repo.get_by_id(product_id)
        if not product:
            raise ValueError(f"Product with ID {product_id} does not exist.")

        qty_dec = Decimal(str(quantity))
        cost_dec = Decimal(str(cost_price)) if cost_price is not None else None
        mrp_dec = Decimal(str(mrp)) if mrp is not None else None

        inv = self.inventory_repo.receive_stock(
            product_id=product_id,
            quantity=qty_dec,
            cost_price=cost_dec,
            mrp=mrp_dec,
        )
        self.session.commit()
        return {
            "product_id": product.id,
            "product_name": product.name,
            "unit": product.unit,
            "added_quantity": float(qty_dec),
            "new_stock": float(inv.quantity),
            "cost_price": float(product.cost_price),
            "mrp": float(product.mrp),
        }

    def get_stock(self, product_id: Optional[int] = None, query: Optional[str] = None) -> Dict[str, Any]:
        """Query stock for a specific product ID or product search term."""
        if product_id is not None:
            product = self.product_repo.get_by_id(product_id)
            if not product:
                return {"found": False, "error": f"Product with ID {product_id} not found."}
            stock = self.inventory_repo.get_stock(product.id)
            return {
                "found": True,
                "product_id": product.id,
                "name": product.name,
                "unit": product.unit,
                "stock": float(stock),
                "is_low_stock": stock <= product.reorder_level,
                "mrp": float(product.mrp),
            }

        if query:
            products = self.product_repo.search(query, limit=5)
            if not products:
                return {"found": False, "error": f"No products matching '{query}' found."}
            if len(products) == 1:
                p = products[0]
                stock = self.inventory_repo.get_stock(p.id)
                return {
                    "found": True,
                    "product_id": p.id,
                    "name": p.name,
                    "unit": p.unit,
                    "stock": float(stock),
                    "is_low_stock": stock <= p.reorder_level,
                    "mrp": float(p.mrp),
                }
            return {
                "found": True,
                "multiple_matches": True,
                "matches": [
                    {
                        "product_id": p.id,
                        "name": p.name,
                        "stock": float(self.inventory_repo.get_stock(p.id)),
                        "unit": p.unit,
                        "mrp": float(p.mrp),
                    }
                    for p in products
                ],
            }

        return {"found": False, "error": "Must specify either product_id or query."}

    def get_low_stock(self) -> List[Dict[str, Any]]:
        """List all products currently below reorder level."""
        return self.inventory_repo.get_low_stock()
