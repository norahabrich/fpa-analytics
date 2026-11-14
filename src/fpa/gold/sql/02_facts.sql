-- Faits : une valeur par (trimestre, compte), en millions de dollars (sauf BPA et actions).
CREATE OR REPLACE TABLE fact_financials AS
SELECT
    printf('FY%d-Q%d', q.fiscal_year, q.fiscal_quarter) AS period_key,
    q.account,
    CASE WHEN a.kind IN ('per_share') THEN q.value
         WHEN a.kind = 'average'      THEN q.value / 1e6   -- millions d'actions
         ELSE q.value / 1e6 END        AS value,
    CASE WHEN a.kind = 'per_share' THEN 'USD/action'
         WHEN a.kind = 'average'   THEN 'millions d''actions'
         ELSE 'MUSD' END               AS unit,
    q.method, q.concept, q.accn, q.restated
FROM silver_quarterly q
JOIN account_mapping a USING (account);

-- Guidance de la direction (référentiel saisi et sourcé en phase 1).
CREATE OR REPLACE TABLE fact_guidance AS
SELECT issued_date::DATE AS issued_date,
       fiscal_year AS fiscal_year_label,
       CAST(substr(fiscal_year, 3) AS INT) AS fiscal_year,
       period, metric, low, high, point,
       coalesce(point, (low + high) / 2, low, high) AS midpoint,
       unit, quote_en, source_url, note
FROM guidance;
