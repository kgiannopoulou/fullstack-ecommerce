# Data Quality Framework

Data quality is measured, not assumed. The rules live in code
([`src/validate.py`](../src/validate.py)), run on every pipeline execution, and are unit-tested
([`tests/test_validation.py`](../tests/test_validation.py)). The same results feed the
*Data Quality* page of the Power BI report and the Excel workbook.

## Scorecard

| Metric | Raw export | Clean warehouse | Definition |
|---|---:|---:|---|
| Records | 340,795 | 338,182 | transaction lines |
| Completeness | 97.9% | 98.1% | records with every required field present |
| Validity | 54.0% | 100.0% | records passing every validity and consistency rule |
| Duplicates | 0.71% | 0.00% | repeated transaction IDs |
| Missing values | 0.19% | 0.27% | empty cells across required fields |
| Failed checks | 12 of 13 | 0 of 15 | rules above their tolerated failure rate |

The raw export is *expected* to fail: that is why the cleaning step exists. The clean warehouse is a
**gate**: if a critical rule fails there, `pipeline.py` stops before any report is rebuilt, so a
broken load can never reach a dashboard. Non-critical rules (guest checkouts, unknown payment method)
have a tolerated rate agreed with the business and are reported as warnings above it.

## Dimensions

| Dimension | Question it answers |
|---|---|
| Completeness | Is the value there? |
| Validity | Is the value possible (positive quantity, plausible price, real date)? |
| Uniqueness | Is each record recorded once? |
| Consistency | Does it agree with other data (standard codes, keys that exist, amounts that add up)? |

## Rules and latest results

### Raw export (before cleaning)

| Rule | Dimension | Table.column | Rule | Failures | Rate | Tolerated | Status |
|---|---|---|---|---:|---:|---:|---|
| R01 | Uniqueness | `transactions.transaction_id` | Each transaction ID appears once | 2,435 | 0.71% | 0% | ❌ FAIL |
| R02 | Completeness | `transactions.customer_id` | Customer ID present (guest checkout allowed up to 3%) | 5,513 | 1.62% | 3% | ✅ PASS |
| R03 | Completeness | `transactions.category` | Category present | 696 | 0.20% | 0% | ❌ FAIL |
| R04 | Completeness | `transactions.payment_method` | Payment method present | 871 | 0.26% | 0% | ❌ FAIL |
| R05 | Completeness | `transactions.shipping_cost` | Shipping cost present on shipped orders | 2,885 | 0.85% | 0% | ❌ FAIL |
| R06 | Validity | `transactions.quantity` | Quantity is a positive integer | 134 | 0.04% | 0% | ❌ FAIL |
| R07 | Validity | `transactions.unit_price` | Unit price > 0 and at most 5x the list price | 44 | 0.01% | 0% | ❌ FAIL |
| R08 | Validity | `transactions.order_date` | Order date in ISO format (YYYY-MM-DD hh:mm:ss) | 115,937 | 34.02% | 0% | ❌ FAIL |
| R09 | Consistency | `transactions.customer_country` | Country uses the standard English name | 40,825 | 11.98% | 0% | ❌ FAIL |
| R10 | Consistency | `transactions.order_status` | Order status uses the standard lower-case code | 23,731 | 6.96% | 0% | ❌ FAIL |
| R11 | Uniqueness | `inventory.product_id, snapshot_date` | One stock count per product per day | 513 | 0.20% | 0% | ❌ FAIL |
| R12 | Validity | `inventory.stock_on_hand` | Stock on hand is not negative | 380 | 0.15% | 0% | ❌ FAIL |
| R13 | Consistency | `customers.country` | Customer country uses the standard English name | 11,026 | 11.98% | 0% | ❌ FAIL |

### Clean warehouse (pipeline gate)

| Rule | Dimension | Table.column | Rule | Failures | Rate | Tolerated | Status |
|---|---|---|---|---:|---:|---:|---|
| C01 | Uniqueness | `order_items.transaction_id` | Each transaction ID appears once | 0 | 0.00% | 0% | ✅ PASS |
| C02 | Uniqueness | `orders.order_id` | Each order appears once | 0 | 0.00% | 0% | ✅ PASS |
| C03 | Completeness | `orders.customer_id` | Customer ID present (guest checkout allowed up to 3%) | 2,316 | 1.60% | 3% | ✅ PASS |
| C04 | Completeness | `orders.payment_method` | Payment method known (Unknown allowed up to 1%) | 376 | 0.26% | 1% | ✅ PASS |
| C05 | Validity | `order_items.quantity` | Quantity > 0 | 0 | 0.00% | 0% | ✅ PASS |
| C06 | Validity | `order_items.unit_price` | Unit price > 0 | 0 | 0.00% | 0% | ✅ PASS |
| C07 | Validity | `orders.status` | Status is completed, refunded or cancelled | 0 | 0.00% | 0% | ✅ PASS |
| C08 | Validity | `orders.country` | Country is one of the 8 markets | 0 | 0.00% | 0% | ✅ PASS |
| C09 | Validity | `orders.shipping_cost` | Shipped orders have a shipping cost > 0 | 0 | 0.00% | 0% | ✅ PASS |
| C10 | Validity | `inventory_daily.stock_on_hand` | Stock on hand >= 0 | 0 | 0.00% | 0% | ✅ PASS |
| C11 | Consistency | `order_items.product_id` | Every line points to a known product | 0 | 0.00% | 0% | ✅ PASS |
| C12 | Consistency | `order_items.order_id` | Every line belongs to a known order | 0 | 0.00% | 0% | ✅ PASS |
| C13 | Consistency | `orders.delivery_date` | Delivery is not before the order | 0 | 0.00% | 0% | ✅ PASS |
| C14 | Consistency | `orders.refund_amount` | Only refunded orders carry a refund | 0 | 0.00% | 0% | ✅ PASS |
| C15 | Consistency | `order_items.net_amount` | Net amount = gross - discount | 0 | 0.00% | 0% | ✅ PASS |

## How a defect is handled

Finding a defect is half the job; each one also needs a business decision (remove, repair, label or
keep). Those decisions and their reasons are in [data_quality_report.md](data_quality_report.md), and
the SQL profiling that reproduces every count is [`sql/01_data_quality_checks.sql`](../sql/01_data_quality_checks.sql).
