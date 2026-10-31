// Power Query (M) - works in Power BI Desktop and in Excel (Data > Get Data > Blank Query).
// One query per reporting view. Requires the analytics database running:
//   docker compose up -d analytics-db && python analytics/run_pipeline.py
// Credentials: Database, user "analyst", password "analyst" (local demo only).

// --- Source (shared) ---
let
    Source = PostgreSQL.Database("localhost:5439", "analytics")
in
    Source

// --- fact_orders ---
let
    Source = PostgreSQL.Database("localhost:5439", "analytics"),
    Data = Source{[Schema = "reporting", Item = "fact_orders"]}[Data],
    Typed = Table.TransformColumnTypes(Data, {
        {"order_date", type date}, {"net_revenue", Currency.Type}, {"gross_amount", Currency.Type},
        {"discount_amount", Currency.Type}, {"refund_amount", Currency.Type}, {"cogs", Currency.Type},
        {"is_late", type logical}, {"is_fulfilled", type logical}, {"has_bulk", type logical}})
in
    Typed

// --- fact_sales ---
let
    Source = PostgreSQL.Database("localhost:5439", "analytics"),
    Data = Source{[Schema = "reporting", Item = "fact_sales"]}[Data],
    Typed = Table.TransformColumnTypes(Data, {
        {"order_date", type date}, {"net_revenue", Currency.Type}, {"gross_profit", Currency.Type}})
in
    Typed

// --- dim_date ---
let
    Source = PostgreSQL.Database("localhost:5439", "analytics"),
    Data = Source{[Schema = "reporting", Item = "dim_date"]}[Data],
    Typed = Table.TransformColumnTypes(Data, {{"date", type date}})
in
    Typed

// --- dim_product ---
let
    Source = PostgreSQL.Database("localhost:5439", "analytics"),
    Data = Source{[Schema = "reporting", Item = "dim_product"]}[Data]
in
    Data

// --- dim_customer ---
let
    Source = PostgreSQL.Database("localhost:5439", "analytics"),
    Data = Source{[Schema = "reporting", Item = "dim_customer"]}[Data],
    // Customers who signed up but never bought have no segment metrics
    Buyers = Table.SelectRows(Data, each [rfm_segment] <> "No purchase")
in
    Buyers

// --- inventory_status ---
let
    Source = PostgreSQL.Database("localhost:5439", "analytics"),
    Data = Source{[Schema = "reporting", Item = "inventory_status"]}[Data]
in
    Data

// --- cohort_retention ---
let
    Source = PostgreSQL.Database("localhost:5439", "analytics"),
    Data = Source{[Schema = "reporting", Item = "cohort_retention"]}[Data],
    Typed = Table.TransformColumnTypes(Data, {{"cohort", type date}})
in
    Typed
