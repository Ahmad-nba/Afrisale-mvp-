"""
Standalone product search test.
Runs hybrid search directly without starting the agent runtime.
"""

from app.core.database import SessionLocal
from app.services.catalog import search_products


def main() -> None:
    query = "shorts"
    db = SessionLocal()
    try:
        results = search_products(db, query=query)
        print(f"Query: {query!r}")
        if not results:
            print("No products found.")
            return

        print("Top matches:")
        for idx, row in enumerate(results[:5], start=1):
            print(
                f"{idx}. {row.get('title', '')} | score={row.get('score', 0):.1f} | "
                f"price={row.get('price')} | product_id={row.get('product_id')}"
            )
            description = str(row.get("description", "")).strip()
            if description:
                print(f"   description: {description}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
