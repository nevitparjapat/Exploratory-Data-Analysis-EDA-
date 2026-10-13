"""Builds the EDA report (Markdown) following the structure planned in the Week 3 design document.
All numbers come from the data, so rerunning on new data gives a new, consistent report."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd

from . import analysis as an


def md_table(df: pd.DataFrame, floatfmt="{:,.2f}") -> str:
    if df.empty:
        return "_No data._\n"
    cols = [str(c) for c in df.columns]
    rows = []
    for _, r in df.iterrows():
        cells = []
        for v in r:
            if isinstance(v, float):
                cells.append(floatfmt.format(v))
            else:
                cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols), *rows]) + "\n"


def _recommendations(df) -> list[str]:
    """Rule-based suggestions. They are starting points to confirm with domain experts, not conclusions."""
    recs = []
    reg = an.regional_production(df)
    low = reg.sort_values("median_yield_per_ha").iloc[0]
    recs.append(f"Review agronomy support and input supply in {low['district']}, which has the lowest median yield per hectare "
                f"({low['median_yield_per_ha']:.1f} quintals); first check whether crop mix explains the gap.")
    sh = an.seasonal_share(df)
    if sh.max() >= 60:
        recs.append(f"Plan storage and transport for the {sh.idxmax()} peak ({sh.max():.0f}% of output) and look at ways to spread risk across seasons.")
    ps = an.price_summary(df)
    risky = ps.sort_values("price_cv_pct", ascending=False).iloc[0]
    recs.append(f"Watch price risk for {risky['crop_type']} (coefficient of variation {risky['price_cv_pct']:.1f}%), the most volatile crop in this data.")
    flagged = an.detect_anomalies(df)
    if flagged["anomaly"].any():
        recs.append("Verify the flagged yield records at the source before using them for decisions (see the anomaly section).")
    imp = an.imputed_share_by_district(df)
    if not imp.empty:
        worst = imp.set_index("district").mean(axis=1).sort_values(ascending=False)
        recs.append(f"Improve data collection in {worst.index[0]}, where the largest share of values had to be imputed ({worst.iloc[0]:.1f}% on average).")
    return recs


def build_report(df: pd.DataFrame, fig_dir: str | Path, out_path: str | Path, source: str = "") -> Path:
    out_path = Path(out_path)
    rel = Path(os.path.relpath(fig_dir, out_path.parent))
    fig = lambda name: f"![{name}]({rel.as_posix()}/{name})"  # noqa: E731

    findings = an.key_findings(df)
    cc = an.confounding_check(df)
    flagged = an.detect_anomalies(df)
    seas = an.seasonal_production(df)

    L = []
    add = L.append
    add("# Exploratory Data Analysis Report: Agribusiness Trends\n")
    add(f"_Generated on {date.today():%d %B %Y} from `{source or 'input data'}` ({len(df):,} records, "
        f"{df['district'].nunique()} districts, {df['crop_type'].nunique()} crops, "
        f"{df['season_year'].nunique()} years)._\n")

    add("## 1. Executive summary\n")
    for s in findings:
        add(f"- {s}")
    add("")

    add("## 2. Introduction and objectives\n")
    add("This report explores cleaned farm-level data to answer five questions: where production is concentrated, "
        "how production and prices change over seasons and years, which factors go with higher yield, which crops carry "
        "the most price risk, and which records look unusual enough to verify.\n")

    add("## 3. Data description\n")
    add(f"- Records: **{len(df):,}**; districts: **{', '.join(sorted(df['district'].unique()))}**")
    add(f"- Crops: **{', '.join(sorted(df['crop_type'].unique()))}**; years: **{', '.join(str(int(y)) for y in sorted(df['season_year'].unique()))}**")
    add(f"- Total area: **{df['area_ha'].sum():,.0f} ha**; total production: **{df['yield_qtl'].sum():,.0f} quintals**")
    imp = an.imputed_share_by_district(df)
    if not imp.empty:
        add("\nShare of values that were imputed during cleaning (%), by district:\n")
        add(md_table(imp, "{:.1f}"))
    add("")

    add("## 4. Methodology\n")
    add("- Medians and the interquartile range are reported next to means because yield data is skewed.")
    add("- Yield and price are compared **within each crop**; pooled results are always checked against within-crop results.")
    add("- Anomalies use two signals per crop: the IQR rule (1.5 x IQR) and the modified Z-score (above 3.5, median/MAD).")
    add("- Group differences use the Kruskal-Wallis test with a Bonferroni correction across crops.")
    add("- Redundancy between numeric variables is checked with the variance inflation factor (VIF).\n")

    add("## 5. Univariate analysis\n")
    add(fig("01_yield_distribution.png") + "\n")
    add(md_table(an.yield_summary_by_crop(df)))

    add("## 6. Regional and seasonal analysis\n")
    add(fig("02_regional_production.png") + "\n")
    add(md_table(an.regional_production(df)))
    add(fig("03_seasonal_production.png") + "\n")
    add(md_table(seas))
    kw = an.district_difference_test(df)
    if not kw.empty:
        add("**Do districts differ in yield per hectare within a crop?** (Kruskal-Wallis, Bonferroni-adjusted)\n")
        add(md_table(kw))

    add("## 7. Relationships and drivers\n")
    add(fig("05_rainfall_vs_yield.png") + "\n")
    add(fig("06_correlation_heatmap.png") + "\n")
    add("### Is the strongest correlation real?\n")
    add(f"Pooled across all crops, `{cc['x']}` and `{cc['y']}` have a correlation of **{cc['pooled_r']}**. Within each crop:\n")
    add(md_table(cc["within"]))
    add(fig("07_pooled_vs_within_crop.png") + "\n")
    if cc["confounded"]:
        add("The pooled value is **an effect of crop mix** (a confounding variable; Simpson's paradox), not a real link, "
            "so it should not be reported as an insight.\n")
    add("**Variance inflation factors** (values above 5 to 10 suggest redundant variables):\n")
    add(md_table(an.vif_table(df)))

    add("## 8. Price and profitability\n")
    add(fig("04_price_trend.png") + "\n")
    add(md_table(an.price_summary(df)))

    add("## 9. Anomalies and data issues\n")
    add(fig("08_anomaly_boxplot.png") + "\n")
    add(md_table(an.anomaly_summary(flagged)))
    top = flagged[flagged["anomaly"]].sort_values("mod_z", key=abs, ascending=False).head(10)
    if not top.empty:
        add("Ten most extreme flagged records (raw yield per hectare before capping):\n")
        add(md_table(top[["farm_id", "district", "crop_type", "yield_per_ha_raw", "mod_z"]]))
    add("Flagged records are not deleted. Each one should be checked against its source; if it cannot be verified it stays flagged "
        "and results are reported with and without it.\n")

    add("## 10. Insights and recommendations\n")
    add("_Rule-based starting points. Each should be confirmed with a domain expert before action._\n")
    for r in _recommendations(df):
        add(f"- {r}")
    add("")

    add("## 11. Limitations and next steps\n")
    add("- If the input is synthetic (as the bundled sample is), the numbers show how the method works and are not real agricultural findings.")
    add("- A few years of data cannot separate a trend from normal year-to-year variation.")
    add("- Imputed values can weaken real relationships; rerun key results on complete records only.")
    add("- Next steps: add weather and soil-type data, test lagged rainfall effects, and build a yield forecasting model on the variables that survive the within-crop checks.\n")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(L), encoding="utf-8")
    return out_path
