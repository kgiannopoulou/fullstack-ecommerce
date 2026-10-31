# Findings and Recommendations

**To:** Head of Operations · **Period:** January 2024 – December 2025 · **Data:** 340,795 raw transaction records, 338,182 valid after cleaning

Every number below comes from a query in [`sql/`](../sql) (IDs such as `Q02.2` link to the saved
result in [`output/`](output/index.md)) or from a test in [statistical_tests.md](statistical_tests.md).
Revenue means **net revenue** (completed order revenue − discounts − refunds), see the
[KPI dictionary](../docs/kpi_dictionary.md).

## Summary

| | 2024 | 2025 | Change |
|---|---:|---:|---:|
| Net revenue | €9.64M | €12.46M | **+29.2%** |
| Fulfilled orders | 56,994 | 79,966 | +40.3% |
| Average order value | €169.16 | €155.78 | **−7.9%** |
| Active customers | 41,403 | 49,543 | +19.7% |
| Refund rate | 4.23% | 3.78% | −0.45 pp |
| Cancellation rate | 5.39% | 5.42% | flat |

1. **Growth is real and steady**: +26–28% year over year on a rolling 90-day basis in both halves of 2025, not a one-off Black Friday effect.
2. **The loyalty programme works**: 90-day repeat purchasing rose from 27.8% to ~41% from the month it launched, and the effect holds when delivery speed is held constant.
3. **Late deliveries cost customers**: a late first delivery cuts the chance of a second order by about a third, and late orders are refunded twice as often.
4. **Twelve best-sellers keep running out**: A-class products with repeated stockouts are 8.2% of 2025 revenue and lost an estimated €133k of sales.
5. **The average order is shrinking because of product mix, not pricing**: like-for-like prices rose 2%, but customers shifted to cheaper categories.

---

## 1. How is the business performing?

**Observation.** Net revenue grew 29.2% to €12.46M (`Q02.2`). Orders grew faster (+40.3%) than revenue,
so the average order value fell 7.9%, from €169.16 to €155.78. Gross margin held at 45% (`Q02.1`).

**Investigation.** Is the growth seasonal? Black Friday week and the first days of December are the
biggest days of each year (`Q03.6`). Every statistical anomaly in `Q10.1` with |z| > 5 falls in Black Friday week, on Cyber Monday or on 1 November 2024, when the November promotions started.
But the rolling 90-day revenue is up 26.0% at the end of June 2025 and 27.8% at the end of December
(`Q03.5`). Both halves of the year grew, so the growth is underlying, not seasonal.

Why did AOV fall? It isn't bulk orders: removing them barely moves the mean (`Q02.3`), and the
drop is still significant without them (−€13.70, 95% CI −€15.23 to −€12.11, statistical test 5).
It isn't pricing either: the same products cost 2.15% more in 2025 (`Q03.8`). What changed is the
mix. Revenue per unit fell 8.7% while the share of low-price categories (phone accessories, office,
home & kitchen) rose from 10.9% to 14.5%, and premium wearables fell 48.5% (`Q04.1`).

**Recommendation.** Report AOV next to units per order and revenue per unit, otherwise the drop will
be misread as discounting. To lift basket value, bundle low-price accessories with A-class
products (e.g. phone case + charger + power bank) rather than discounting the cheap items further.

## 2. Which products and categories drive or hurt revenue?

**Observation.** Revenue is concentrated: **70 SKUs (18.9% of the catalogue) produce 80.2% of revenue**,
while 177 C-class SKUs (47.7%) produce 5% (`Q04.3`). Three categories (Computer Accessories, Audio,
Bags & Travel) make up 64% of revenue (`Q04.1`).

**Investigation.** Two categories shrank in a growing business: Wearables (−48.5%) and Audio (−13.8%).
`Q04.5` traces them to a handful of products:

| Product | H2 2024 | H2 2025 | Change |
|---|---:|---:|---:|
| Fitness Band O174 | €523,518 | €0 | −100% (discontinued) |
| Earbuds Max P729 | €635,181 | €162,612 | −74% |
| Mechanical Keyboard Pro Q322 | €412,084 | €206,949 | −50% |

Earbuds Max and Mechanical Keyboard Pro also declined three months in a row more than once in 2025 (`Q04.4`).
Was that a supply problem? `Q08.6` shows both were **in stock every single day of 2025**, so customers
stopped buying them. The shelves weren't empty.

**Recommendation.** Treat the two declining best-sellers as a demand problem: check competitor
prices and reviews, and plan their replacements before the next peak season. Decide what replaces
the discontinued Fitness Band: it was the single largest product in H2 2024 and nothing has filled the gap.

## 3. Are customers returning after their first purchase?

**Observation.** 34.3% of customers have ordered more than once, and those customers generate 57.2% of
revenue (`Q05.1`). Among those who return, 43% place the second order within 30 days and 89% within 90 days (`Q05.4`).

**Investigation: cohorts.** The cohort matrix (`Q07.1`) shows a step change: Month-1 retention is
12–15% for every cohort up to February 2025, then 18.6–21.1% from March 2025 on. Comparing the same
calendar months a year apart rules out seasonality (`Q07.2`):

| First order in | Jan | Feb | **Mar** | Apr | May | Jun | Jul | Aug | Sep |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2024, 90-day repeat | 27.9% | 28.6% | 28.0% | 27.9% | 29.2% | 27.3% | 29.2% | 26.8% | 26.5% |
| 2025, 90-day repeat | 28.0% | 28.2% | **39.8%** | 40.2% | 40.3% | 41.9% | 40.8% | 40.2% | 42.0% |

Two things changed in 2025: the **loyalty programme** (1 March) and a **faster courier in Greece**
(15 May). Splitting by period and by whether the first delivery arrived late (`Q07.3`) separates them:

- the jump happens in March, before the courier change, and it shows up among on-time *and* late deliveries, which points to the loyalty programme;
- a late first delivery lowers repeat purchasing in every period (22.5% vs 33.5% before the programme, 33.2% vs 45.7% after).

**Explanation.** Decomposing the +13.5 pp improvement (`Q07.5`): **+11.3 pp comes from the loyalty
programme and +2.1 pp from fewer late deliveries.** The courier switch raised on-time delivery in Greece from
36.6% to 67.9% (`Q09.2`) and cut late first deliveries from 63% to 32% (`Q07.4`). The statistical tests
confirm both effects (tests 1–3). The loyalty effect is +12.0 pp even among on-time deliveries.

**Segments.** RFM segmentation (`Q06.1`, `Q06.2`):

| Segment | Customers | Revenue | Revenue per customer |
|---|---:|---:|---:|
| Champions | 3.0% | 9.0% | €733 |
| Loyal | 6.6% | 13.3% | €500 |
| Cannot Lose Them | 2.7% | 6.2% | €576 |
| At Risk | 7.7% | 10.6% | €343 |
| Lost | 15.3% | 10.4% | €169 |

**At Risk and Cannot Lose Them are 10.4% of customers but 16.8% of historical revenue.** They have
bought 2–3+ times and have been silent for ~17 months on average. That makes them a better
retention target than the larger Lost group, whose members bought only once.

**Recommendations.**
1. Keep the loyalty programme and push the second order: the 30-day window after the first purchase is where most returning customers come back.
2. Run a win-back campaign for the 9,050 At Risk / Cannot Lose Them customers before spending on the Lost group (`Q06.3` lists the most valuable ones).
3. Shift acquisition budget toward channels whose customers return: Email (41.7% repeat) and Direct (38.4%) against Marketplace (25.0%) (`Q05.5`).

## 4. Which products are at risk of stockout or overstock?

**Observation.** Position on 31 December 2025 (`Q08.2`):

| Status | Products | Stock value (cost) | Action |
|---|---:|---:|---|
| CRITICAL (cover < lead time) | 20 (4 A-class) | €3.7k | Reorder now; expedite A items |
| HIGH RISK (cover < lead time + 7 days) | 47 | €72k | Reorder this week |
| OVERSTOCK (> 120 days of cover) | 32 | €158k (19% of stock value) | Pause purchasing |
| DEAD STOCK (no sales in 90 days) | 11 | €2k | Clear |
| HEALTHY | 250 | €589k | Monitor |

**Investigation.** Stockouts are concentrated where they hurt most. In 2025, **12 A-class products had three
or more separate stockout episodes**, averaging 39 days out of stock each. Together they make up 8.2% of 2025
revenue, and they lost an **estimated €133k of sales** (demand on in-stock days × days out of stock ×
average price, `Q08.4`). The worst single SKU, Laptop Stand Lite B655, ran out 9 times (`Q08.3`).

**Explanation.** The repeated short episodes (5–10 days each) fit a reorder point set too low for the
lead time on those SKUs, not a supplier failure. One SKU (Earbuds Pro X359) has been out of stock for 221 days
in a row. That looks like a delisting rather than a lost sale, and it is flagged for confirmation instead
of being counted.

Turnover varies from 15.8× a year (Phone Accessories) to 5.7× (Fitness, 64 days of inventory, `Q08.5`).
Most overstocked SKUs are slow B/C items, but most of the money is in a few larger lines: 3 A-class SKUs hold €67k and 11 B-class SKUs €69k (`Q11.3`). At current sales their stock lasts anywhere from 4 months to more than 3 years.

**Recommendations.**
1. Raise safety stock on the 12 repeatedly out-of-stock A-class SKUs. Recovering even half of the lost sales is worth ~€65k a year in revenue.
2. Pause purchase orders for the 32 overstocked SKUs and release the €158k tied up in them through bundles with A-class products.
3. Record open purchase orders in the data. Without them the days-of-cover figures can't account for stock already on its way.

## 5. What should management do next?

Ranked by estimated impact and effort:

| # | Action | Why (evidence) | Owner |
|---:|---|---|---|
| 1 | Keep and extend the loyalty programme, focusing on the second order within 30 days | +11.3 pp 90-day repeat rate (`Q07.5`, test 2) | Marketing |
| 2 | Bring delivery abroad to the Greek standard (only 51–72% on time with DHL) | Late first delivery: 25.9% vs 38.2% repeat; late orders refunded 5.6% vs 2.6% (`Q09.2`, `Q09.3`, test 3) | Operations |
| 3 | Ship weekend orders on weekends | 84% of Sat/Sun orders wait 2+ days to ship vs 50% on weekdays (`Q09.4`) | Warehouse |
| 4 | Raise safety stock on 12 A-class SKUs; pause buying for 32 overstocked SKUs | ~€133k lost sales; €158k tied up (`Q08.4`, `Q08.2`) | Purchasing |
| 5 | Win back At Risk / Cannot Lose Them customers | 10.4% of customers, 16.8% of revenue (`Q06.2`) | CRM |
| 6 | Reduce cash-on-delivery cancellations (confirmation call, prepayment incentive) | COD is cancelled 10.2% of the time vs ~4.5%; €401k of cancelled orders over two years (`Q02.4`, test 6) | E-commerce |
| 7 | Investigate the decline of Earbuds Max and Mechanical Keyboard Pro | −€678k combined H2 vs H2, with stock available (`Q04.5`, `Q08.6`) | Category management |
| 8 | Fix the data at the source | 47.5% of raw records needed a fix (`Q01.11`): duplicate re-sends, four date formats, 25 spellings of eight countries | IT / Data |

## Limits of this analysis

- The data is simulated (see [`analytics/generate_data.py`](../analytics/generate_data.py)), with realistic defects and business events built in. The methods carry over to real data; the numbers do not.
- Before/after comparisons are observational. A holdout group in the next loyalty campaign would measure its effect directly.
- Lost-sales estimates assume demand during a stockout equals demand on in-stock days. Some customers would have bought a substitute instead, so the figure is an upper bound.
