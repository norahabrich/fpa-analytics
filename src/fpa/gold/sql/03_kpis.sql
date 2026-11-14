-- Indicateurs trimestriels réconciliés, prêts pour Power BI.
CREATE OR REPLACE TABLE kpi_quarterly AS
WITH w AS (
    PIVOT (SELECT period_key, account, value FROM fact_financials)
    ON account USING first(value) GROUP BY period_key
), k AS (
    SELECT
        p.period_key, p.fiscal_year, p.fiscal_quarter, p.period_end, p.days, p.weeks,
        w.revenue,
        w.cogs,
        w.revenue - w.cogs                                AS gross_margin,
        (w.revenue - w.cogs) / w.revenue                  AS gross_margin_rate,
        w.sga,
        w.sga / w.revenue                                 AS sga_rate,
        w.operating_income + w.da_total                   AS ebitda,
        (w.operating_income + w.da_total) / w.revenue     AS ebitda_margin,
        w.operating_income,
        w.operating_income / w.revenue                    AS operating_margin_rate,
        w.net_income,
        w.eps_diluted,
        w.cfo,
        w.capex,
        w.cfo - w.capex                                   AS free_cash_flow,
        w.inventory,
        w.accounts_payable,
        w.inventory / w.cogs * p.days                     AS dio_days,
        w.accounts_payable / w.cogs * p.days              AS dpo_days,
        w.inventory - w.accounts_payable                  AS inventory_net_of_payables,
        w.cash,
        coalesce(w.current_debt, 0) + w.long_term_debt    AS gross_debt,
        coalesce(w.current_debt, 0) + w.long_term_debt - w.cash AS net_debt
    FROM dim_period p JOIN w USING (period_key)
)
SELECT k.*,
       revenue / lag(revenue) OVER (PARTITION BY fiscal_quarter ORDER BY fiscal_year) - 1 AS revenue_yoy,
       operating_margin_rate - lag(operating_margin_rate) OVER (PARTITION BY fiscal_quarter ORDER BY fiscal_year) AS operating_margin_yoy_pts,
       sum(revenue) OVER t           AS revenue_ttm,
       sum(operating_income) OVER t / sum(revenue) OVER t AS operating_margin_ttm,
       sum(free_cash_flow) OVER t    AS free_cash_flow_ttm
FROM k
WINDOW t AS (ORDER BY fiscal_year, fiscal_quarter ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)
ORDER BY fiscal_year, fiscal_quarter;

-- Indicateurs annuels : exercices complets uniquement (4 trimestres).
CREATE OR REPLACE TABLE kpi_annual AS
SELECT
    fiscal_year,
    printf('FY%d', fiscal_year) AS fiscal_year_label,
    sum(weeks)                  AS weeks,
    sum(revenue)                AS revenue,
    sum(gross_margin)           AS gross_margin,
    sum(gross_margin) / sum(revenue) AS gross_margin_rate,
    sum(sga) / sum(revenue)     AS sga_rate,
    sum(ebitda)                 AS ebitda,
    sum(operating_income)       AS operating_income,
    sum(operating_income) / sum(revenue) AS operating_margin_rate,
    sum(net_income)             AS net_income,
    sum(cfo)                    AS cfo,
    sum(capex)                  AS capex,
    sum(free_cash_flow)         AS free_cash_flow,
    last(inventory ORDER BY fiscal_quarter)        AS inventory_end,
    last(accounts_payable ORDER BY fiscal_quarter) AS accounts_payable_end,
    last(net_debt ORDER BY fiscal_quarter)         AS net_debt_end
FROM kpi_quarterly
GROUP BY fiscal_year
HAVING count(*) = 4
ORDER BY fiscal_year;
