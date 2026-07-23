-- Compute monthly P&L from raw tables following DEMO-FINANCIAL-CONSULTOR.md recipe
-- This is the "consultant's Excel" — bottom-up reconstruction from source tables
-- with all DQ filters applied. Output should match telco_demo.pl_monthly within 1-2%.

WITH months AS (
  SELECT DISTINCT date_trunc('month', d)::date AS month
  FROM (
    SELECT recharge_date AS d FROM telco_demo.recharges
    UNION ALL SELECT payment_date FROM telco_demo.payments
    UNION ALL SELECT cost_date FROM telco_demo.interconnect_costs_daily
    UNION ALL SELECT month FROM telco_demo.network_costs_monthly
    UNION ALL SELECT month FROM telco_demo.payroll_monthly
    UNION ALL SELECT month FROM telco_demo.marketing_spend
  ) x
  WHERE d IS NOT NULL
),
rev_prepaid AS (
  SELECT date_trunc('month', recharge_date)::date AS month,
         SUM(amount) AS revenue_prepaid
  FROM telco_demo.recharges
  WHERE amount > 0 AND amount < 1000
  GROUP BY 1
),
rev_postpaid AS (
  SELECT date_trunc('month', payment_date)::date AS month,
         SUM(amount) AS revenue_postpaid
  FROM telco_demo.payments
  WHERE status = 'completed' AND amount > 0 AND amount < 10000
  GROUP BY 1
),
cogs_inter AS (
  SELECT date_trunc('month', cost_date)::date AS month,
         SUM(total_cost) AS cogs_interconnect
  FROM telco_demo.interconnect_costs_daily
  GROUP BY 1
),
cogs_net AS (
  SELECT month::date AS month,
         SUM(total_cost) AS cogs_network
  FROM telco_demo.network_costs_monthly
  GROUP BY 1
),
opex_mkt AS (
  SELECT month::date AS month,
         SUM(spend) AS opex_marketing
  FROM telco_demo.marketing_spend
  GROUP BY 1
),
opex_pay AS (
  SELECT month::date AS month,
         SUM(total_cost) AS opex_payroll
  FROM telco_demo.payroll_monthly
  GROUP BY 1
),
chargebacks_m AS (
  -- chargebacks.amount tiene outliers DQ ($99K+); aplicar el mismo filtro que payments
  SELECT date_trunc('month', requested_at)::date AS month,
         SUM(amount) AS chargebacks_amount
  FROM telco_demo.chargebacks
  WHERE amount > 0 AND amount < 10000
  GROUP BY 1
),
ar_latest AS (
  -- 5% del bucket 61-90+ días AT snapshot más reciente, con filtro outliers
  SELECT 0.05 * SUM(total_due) AS ar_provision
  FROM telco_demo.accounts_receivable
  WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM telco_demo.accounts_receivable)
    AND total_due > 0 AND total_due < 10000
    AND risk_bucket IN ('61-90_days', '90+_days')
),
combined AS (
  SELECT m.month,
    COALESCE(rp.revenue_prepaid, 0)        AS revenue_prepaid,
    COALESCE(rpo.revenue_postpaid, 0)      AS revenue_postpaid,
    COALESCE(ci.cogs_interconnect, 0)      AS cogs_interconnect,
    COALESCE(cn.cogs_network, 0)           AS cogs_network,
    COALESCE(om.opex_marketing, 0)         AS opex_marketing,
    COALESCE(op.opex_payroll, 0)           AS opex_payroll,
    COALESCE(cb.chargebacks_amount, 0)     AS chargebacks_amount,
    (SELECT ar_provision FROM ar_latest)   AS ar_provision_global
  FROM months m
  LEFT JOIN rev_prepaid rp   ON rp.month = m.month
  LEFT JOIN rev_postpaid rpo ON rpo.month = m.month
  LEFT JOIN cogs_inter ci    ON ci.month = m.month
  LEFT JOIN cogs_net cn      ON cn.month = m.month
  LEFT JOIN opex_mkt om      ON om.month = m.month
  LEFT JOIN opex_pay op      ON op.month = m.month
  LEFT JOIN chargebacks_m cb ON cb.month = m.month
)
SELECT
  to_char(month, 'YYYY-MM')                                  AS mes,
  ROUND(revenue_prepaid::numeric, 0)                         AS revenue_prepaid,
  ROUND(revenue_postpaid::numeric, 0)                        AS revenue_postpaid,
  ROUND((revenue_prepaid + revenue_postpaid)::numeric, 0)    AS revenue_total,
  ROUND(cogs_interconnect::numeric, 0)                       AS cogs_interconnect,
  ROUND(cogs_network::numeric, 0)                            AS cogs_network,
  ROUND((cogs_interconnect + cogs_network)::numeric, 0)      AS cogs_total,
  ROUND((revenue_prepaid + revenue_postpaid - cogs_interconnect - cogs_network)::numeric, 0) AS gross_profit,
  ROUND(opex_marketing::numeric, 0)                          AS opex_marketing,
  ROUND(opex_payroll::numeric, 0)                            AS opex_payroll,
  ROUND((0.08 * (revenue_prepaid + revenue_postpaid))::numeric, 0) AS opex_g_and_a,
  ROUND((chargebacks_amount + ar_provision_global)::numeric, 0)    AS opex_bad_debt,
  ROUND((opex_marketing + opex_payroll
         + 0.08 * (revenue_prepaid + revenue_postpaid)
         + chargebacks_amount + ar_provision_global)::numeric, 0)  AS opex_total,
  ROUND(((revenue_prepaid + revenue_postpaid)
         - (cogs_interconnect + cogs_network)
         - (opex_marketing + opex_payroll
            + 0.08 * (revenue_prepaid + revenue_postpaid)
            + chargebacks_amount + ar_provision_global))::numeric, 0) AS ebitda,
  ROUND((0.12 * (revenue_prepaid + revenue_postpaid))::numeric, 0)   AS depreciation,
  ROUND((0.015 * (revenue_prepaid + revenue_postpaid))::numeric, 0)  AS interest_expense,
  -- Pre-tax = EBITDA - depr - interest
  -- Net = Pre-tax - 0.25 * GREATEST(Pre-tax, 0)
  ROUND((
    (revenue_prepaid + revenue_postpaid)
    - (cogs_interconnect + cogs_network)
    - (opex_marketing + opex_payroll
       + 0.08 * (revenue_prepaid + revenue_postpaid)
       + chargebacks_amount + ar_provision_global)
    - 0.12 * (revenue_prepaid + revenue_postpaid)
    - 0.015 * (revenue_prepaid + revenue_postpaid)
  )::numeric, 0) AS pre_tax_income,
  ROUND((
    GREATEST(
      (revenue_prepaid + revenue_postpaid)
      - (cogs_interconnect + cogs_network)
      - (opex_marketing + opex_payroll
         + 0.08 * (revenue_prepaid + revenue_postpaid)
         + chargebacks_amount + ar_provision_global)
      - 0.12 * (revenue_prepaid + revenue_postpaid)
      - 0.015 * (revenue_prepaid + revenue_postpaid)
    , 0) * 0.25
  )::numeric, 0) AS taxes,
  ROUND((
    (revenue_prepaid + revenue_postpaid)
    - (cogs_interconnect + cogs_network)
    - (opex_marketing + opex_payroll
       + 0.08 * (revenue_prepaid + revenue_postpaid)
       + chargebacks_amount + ar_provision_global)
    - 0.12 * (revenue_prepaid + revenue_postpaid)
    - 0.015 * (revenue_prepaid + revenue_postpaid)
    - GREATEST(
        (revenue_prepaid + revenue_postpaid)
        - (cogs_interconnect + cogs_network)
        - (opex_marketing + opex_payroll
           + 0.08 * (revenue_prepaid + revenue_postpaid)
           + chargebacks_amount + ar_provision_global)
        - 0.12 * (revenue_prepaid + revenue_postpaid)
        - 0.015 * (revenue_prepaid + revenue_postpaid)
      , 0) * 0.25
  )::numeric, 0) AS net_income
FROM combined
ORDER BY month;
