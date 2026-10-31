"""Create the warehouse schemas and land the raw CSV export untouched."""
import config
import db

TABLES = {
    "raw.products": "raw_products.csv",
    "raw.customers": "raw_customers.csv",
    "raw.transactions": "raw_transactions.csv",
    "raw.inventory": "raw_inventory.csv",
}


def main():
    with db.connect() as conn:
        db.run_file(conn, config.SQL_DIR / "00_schema.sql")
        for table, name in TABLES.items():
            n = db.copy_csv(conn, table, config.DATA_DIR / name)
            print(f"{table:20s} {n:>9,} rows")


if __name__ == "__main__":
    main()
