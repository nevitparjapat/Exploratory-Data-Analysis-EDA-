# Agribusiness EDA Project

This project turns my Week 3 plan for an exploratory data analysis (EDA) report into working code.
Give it a cleaned farm dataset and it produces the charts, summary tables and a written EDA report. There is
also a small dashboard for people who would rather click than run commands.

It continues the Week 2 project (`agri-data-cleaning`): the cleaned file made there is the input here.
A copy of that output is included in `data/sample/` so the project runs straight away.

> The bundled sample data is **synthetic**. The numbers show how the method works and are not real agricultural findings.

## What it does

| Planned in the Week 3 design | Where it is in the code |
|---|---|
| Variables and metrics (regional production, yield per hectare, seasonal share, price volatility, revenue per hectare) | `analysis.py` |
| Univariate, regional, seasonal and price analysis | `analysis.py`, report sections 5 to 8 |
| Correlations, with a check against hidden third factors (Simpson's paradox) and VIF for redundant variables | `confounding_check`, `vif_table` |
| Group tests (Kruskal-Wallis with Bonferroni correction) | `district_difference_test` |
| Anomaly screening with two signals (IQR fences and modified Z-score) | `detect_anomalies` |
| Visualization plan (8 charts, fixed color per crop, one y-axis) | `plots.py` |
| Final report structure (summary, methodology, analysis, anomalies, recommendations, limitations) | `report.py` |

One result worth pointing out: in the sample data, yield per hectare and price have a pooled correlation of
about -0.89, but inside every single crop it is close to zero. The pooled number only reflects the crop mix.
The code checks for this automatically, and chart 07 shows it.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev,dashboard]"

agri-eda                             # figures + tables + reports/eda_report.md
pytest                               # run the tests
streamlit run dashboard/eda_app.py   # interactive dashboard
```

To use your own data: `agri-eda --input my_clean_file.csv --out my_reports`.
The file needs these columns: `farm_id, district, crop_type, season, season_year, area_ha, yield_qtl,
rainfall_mm, soil_ph, fertilizer_kg, market_price`. Columns like `yield_per_ha`, `yield_per_ha_raw`
and the `*_was_missing` flags are used if present.

## Output

```
reports/
  eda_report.md        the written report, numbers computed from the data
  figures/             8 PNG charts
  tables/              summary tables as CSV, including flagged_anomalies.csv
```

## Dashboard

Pick the bundled sample or upload a cleaned CSV, filter by crop, district and year, then look through the tabs:
key findings, regional and seasonal charts, yield distributions, an explorer for any two variables (with the
within-crop check shown next to the pooled correlation), flagged anomalies, and a button that builds the report.

## Project layout

```
src/agri_eda/
  analysis.py   all calculations (return DataFrames, easy to test)
  plots.py      the 8 charts
  report.py     builds the Markdown report
  cli.py        the `agri-eda` command
dashboard/eda_app.py    Streamlit dashboard
data/sample/            cleaned sample data from the Week 2 pipeline
tests/test_eda.py       15 tests
```

## Notes and limits

- Anomalies are flagged, not deleted. Each one should be checked against its source.
- The recommendations in the report are rule-based starting points and need a domain expert's review.
- Three years of data cannot separate a real trend from normal year-to-year variation.
- Every run on the same data gives the same report, apart from the date line.

## License

MIT
