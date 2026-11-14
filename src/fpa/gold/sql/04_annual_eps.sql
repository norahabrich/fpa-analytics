-- BPA annuel publié (non additif : on ne somme pas les BPA trimestriels).
CREATE OR REPLACE TABLE kpi_annual AS
SELECT k.*, a.value AS eps_diluted
FROM kpi_annual k
LEFT JOIN (SELECT fiscal_year, value FROM silver_annual WHERE account = 'eps_diluted') a USING (fiscal_year)
ORDER BY fiscal_year;
