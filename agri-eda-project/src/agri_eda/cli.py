"""Command line entry point:  agri-eda --input data/sample/agri_clean_sample.csv --out reports"""
import argparse
from pathlib import Path

from . import analysis as an
from . import plots
from .report import build_report


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the EDA: figures, tables and a Markdown report.")
    ap.add_argument("--input", default="data/sample/agri_clean_sample.csv", help="cleaned CSV")
    ap.add_argument("--out", default="reports", help="output folder")
    a = ap.parse_args()

    df = an.load_data(a.input)
    out = Path(a.out)
    figs = plots.make_all(df, out / "figures")

    tables = out / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    an.yield_summary_by_crop(df).to_csv(tables / "yield_summary_by_crop.csv", index=False)
    an.regional_production(df).to_csv(tables / "regional_production.csv", index=False)
    an.seasonal_production(df).to_csv(tables / "seasonal_production.csv", index=False)
    an.price_summary(df).to_csv(tables / "price_summary.csv", index=False)
    an.detect_anomalies(df).query("anomaly").to_csv(tables / "flagged_anomalies.csv", index=False)

    report = build_report(df, out / "figures", out / "eda_report.md", source=Path(a.input).name)
    print(f"{len(df):,} records analysed")
    print(f"{len(figs)} figures  -> {out / 'figures'}")
    print(f"5 tables     -> {tables}")
    print(f"Report       -> {report}")
    print("\nKey findings:")
    for s in an.key_findings(df):
        print(" -", s)


if __name__ == "__main__":
    main()
