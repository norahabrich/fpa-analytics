-- Dimensions du modèle en étoile.
-- dim_period : un trimestre fiscal par ligne (FY2022-Q1 = février à avril 2022).
CREATE OR REPLACE TABLE dim_period AS
WITH p AS (
    SELECT fiscal_year, fiscal_quarter,
           max(period_end) AS period_end,
           -- début du trimestre : jour qui suit la clôture du trimestre précédent
           max(period_start) FILTER (WHERE method IN ('reported', 'derived_ytd', 'derived_fy')) AS period_start_raw
    FROM silver_quarterly
    WHERE account = 'revenue'
    GROUP BY ALL
)
SELECT
    printf('FY%d-Q%d', fiscal_year, fiscal_quarter)                         AS period_key,
    fiscal_year,
    fiscal_quarter,
    printf('FY%d', fiscal_year)                                              AS fiscal_year_label,
    coalesce(lag(period_end) OVER w + INTERVAL 1 DAY, period_start_raw)::DATE AS period_start,
    period_end,
    datediff('day', coalesce(lag(period_end) OVER w + INTERVAL 1 DAY, period_start_raw), period_end) + 1 AS days,
    round((datediff('day', coalesce(lag(period_end) OVER w + INTERVAL 1 DAY, period_start_raw), period_end) + 1) / 7)::INT AS weeks
FROM p
WINDOW w AS (ORDER BY fiscal_year, fiscal_quarter);

CREATE OR REPLACE TABLE dim_account AS
SELECT account, label_fr, statement, kind,
       CASE statement WHEN 'IS' THEN 'Compte de résultat' WHEN 'BS' THEN 'Bilan' ELSE 'Flux de trésorerie' END AS statement_label
FROM account_mapping;
