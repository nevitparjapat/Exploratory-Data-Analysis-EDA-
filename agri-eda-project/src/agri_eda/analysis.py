"""Core EDA computations. Every function takes a DataFrame and returns a DataFrame or a plain value,
so they are easy to test and to reuse from the CLI, the report builder and the dashboard."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

REQUIRED = ["farm_id", "district", "crop_type", "season", "season_year",
            "area_ha", "yield_qtl", "rainfall_mm", "soil_ph", "fertilizer_kg", "market_price"]
NUMERIC_DRIVERS = ["area_ha", "yield_per_ha", "rainfall_mm", "soil_ph", "fertilizer_kg", "market_price"]
SEASON_ORDER = ["kharif", "rabi", "zaid"]


# --------------------------------------------------------------------------- loading
def load_data(path) -> pd.DataFrame:
    """Read a cleaned CSV and check that the columns the EDA needs are present."""
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Input file is missing required columns: {', '.join(missing)}")
    if "yield_per_ha" not in df.columns:
        df["yield_per_ha"] = df["yield_qtl"] / df["area_ha"]
    if "yield_per_ha_raw" not in df.columns:
        df["yield_per_ha_raw"] = df["yield_per_ha"]
    if "yield_outlier_flag" not in df.columns:
        df["yield_outlier_flag"] = False
    for c in ("sowing_date", "harvest_date"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    if "crop_duration_days" not in df.columns and {"sowing_date", "harvest_date"} <= set(df.columns):
        df["crop_duration_days"] = (df["harvest_date"] - df["sowing_date"]).dt.days
    return df


def apply_filters(df, crops=None, districts=None, years=None) -> pd.DataFrame:
    out = df
    if crops:
        out = out[out["crop_type"].isin(crops)]
    if districts:
        out = out[out["district"].isin(districts)]
    if years:
        out = out[out["season_year"].isin(years)]
    return out


# --------------------------------------------------------------------------- univariate
def yield_summary_by_crop(df) -> pd.DataFrame:
    g = df.groupby("crop_type")["yield_per_ha"]
    out = pd.DataFrame({
        "records": g.size(), "mean": g.mean(), "median": g.median(), "std": g.std(),
        "iqr": g.quantile(0.75) - g.quantile(0.25), "skew": g.apply(lambda s: s.skew()),
        "cv": g.std() / g.mean(),
    })
    return out.round(2).reset_index()


# --------------------------------------------------------------------------- regional / seasonal
def regional_production(df) -> pd.DataFrame:
    g = df.groupby("district")
    out = pd.DataFrame({
        "farms": g.size(), "total_qtl": g["yield_qtl"].sum(), "area_ha": g["area_ha"].sum(),
        "median_yield_per_ha": g["yield_per_ha"].median(),
    })
    out["share_pct"] = out["total_qtl"] / out["total_qtl"].sum() * 100
    return out.sort_values("total_qtl", ascending=False).round(2).reset_index()


def seasonal_production(df) -> pd.DataFrame:
    t = df.groupby(["season_year", "season"])["yield_qtl"].sum().reset_index(name="total_qtl")
    t["share_of_year_pct"] = t["total_qtl"] / t.groupby("season_year")["total_qtl"].transform("sum") * 100
    t["yoy_change_pct"] = t.sort_values("season_year").groupby("season")["total_qtl"].pct_change() * 100
    t["season"] = pd.Categorical(t["season"], SEASON_ORDER, ordered=True)
    return t.sort_values(["season_year", "season"]).round(2).reset_index(drop=True)


def seasonal_share(df) -> pd.Series:
    s = df.groupby("season")["yield_qtl"].sum()
    return (s / s.sum() * 100).round(1)


# --------------------------------------------------------------------------- price / profitability
def price_summary(df) -> pd.DataFrame:
    g = df.groupby("crop_type")
    out = pd.DataFrame({
        "mean_price": g["market_price"].mean(), "price_std": g["market_price"].std(),
        "mean_yield_per_ha": g["yield_per_ha"].mean(),
    })
    out["price_cv_pct"] = out["price_std"] / out["mean_price"] * 100
    out["revenue_per_ha"] = out["mean_yield_per_ha"] * out["mean_price"]
    return out.sort_values("revenue_per_ha", ascending=False).round(2).reset_index()


def price_index(df) -> pd.DataFrame:
    p = df.groupby(["season_year", "crop_type"])["market_price"].mean().unstack()
    return (p / p.iloc[0] * 100).round(2)


# --------------------------------------------------------------------------- relationships
def pooled_correlation(df, cols=None, method="pearson") -> pd.DataFrame:
    cols = [c for c in (cols or NUMERIC_DRIVERS + ["crop_duration_days"]) if c in df.columns]
    return df[cols].corr(method=method)


def within_crop_correlation(df, x: str, y: str, method="pearson") -> pd.DataFrame:
    rows = [{"crop_type": crop, "n": len(g), "r": g[x].corr(g[y], method=method)}
            for crop, g in df.groupby("crop_type")]
    return pd.DataFrame(rows).round(3)


def confounding_check(df, x="yield_per_ha", y="market_price", threshold=0.5) -> dict:
    """Compare the pooled correlation with the within-crop ones. A big gap suggests the crop mix
    (a hidden third factor) is driving the pooled number (Simpson's paradox)."""
    pooled = df[x].corr(df[y])
    within = within_crop_correlation(df, x, y)
    max_within = within["r"].abs().max()
    return {"x": x, "y": y, "pooled_r": round(pooled, 3), "max_abs_within_r": round(max_within, 3),
            "within": within, "confounded": bool(abs(pooled) >= threshold and max_within < 0.3)}


def vif_table(df, cols=None) -> pd.DataFrame:
    """Variance inflation factor, computed with plain least squares (no extra dependency)."""
    cols = [c for c in (cols or NUMERIC_DRIVERS) if c in df.columns]
    X = df[cols].dropna().to_numpy(dtype=float)
    X = (X - X.mean(axis=0)) / X.std(axis=0, ddof=0)
    out = []
    for i, c in enumerate(cols):
        y = X[:, i]
        A = np.delete(X, i, axis=1)
        beta, *_ = np.linalg.lstsq(A, y, rcond=None)
        r2 = 1 - ((y - A @ beta) ** 2).sum() / ((y - y.mean()) ** 2).sum()
        out.append({"variable": c, "vif": 1 / (1 - r2) if r2 < 1 else np.inf})
    return pd.DataFrame(out).round(2)


def district_difference_test(df) -> pd.DataFrame:
    """Kruskal-Wallis test: does yield per hectare differ between districts, inside each crop?"""
    rows = []
    for crop, g in df.groupby("crop_type"):
        groups = [s["yield_per_ha"].to_numpy() for _, s in g.groupby("district") if len(s) >= 5]
        if len(groups) >= 2:
            h, p = stats.kruskal(*groups)
            rows.append({"crop_type": crop, "districts": len(groups), "H": round(h, 2), "p_value": round(p, 4)})
    out = pd.DataFrame(rows)
    if not out.empty:  # Bonferroni correction for running one test per crop
        out["p_adjusted"] = (out["p_value"] * len(out)).clip(upper=1).round(4)
        out["significant_5pct"] = out["p_adjusted"] < 0.05
    return out


# --------------------------------------------------------------------------- anomalies
def detect_anomalies(df, col="yield_per_ha_raw", by="crop_type", k=1.5, z_cut=3.5) -> pd.DataFrame:
    """Two independent signals per group: IQR fences and the modified Z-score (median / MAD)."""
    out = df.copy()
    grp = out.groupby(by)[col]
    q1, q3 = grp.transform(lambda s: s.quantile(0.25)), grp.transform(lambda s: s.quantile(0.75))
    iqr = q3 - q1
    out["iqr_flag"] = (out[col] < q1 - k * iqr) | (out[col] > q3 + k * iqr)
    med = grp.transform("median")
    mad = (out[col] - med).abs().groupby(out[by]).transform("median")
    out["mod_z"] = np.where(mad > 0, 0.6745 * (out[col] - med) / mad, 0.0)
    out["mod_z_flag"] = out["mod_z"].abs() > z_cut
    out["anomaly"] = out["iqr_flag"] | out["mod_z_flag"]
    out["both_signals"] = out["iqr_flag"] & out["mod_z_flag"]
    return out


def anomaly_summary(df_flagged) -> pd.DataFrame:
    g = df_flagged.groupby("crop_type")
    return pd.DataFrame({"records": g.size(), "iqr_flagged": g["iqr_flag"].sum(),
                         "mod_z_flagged": g["mod_z_flag"].sum(), "both": g["both_signals"].sum()}).reset_index()


# --------------------------------------------------------------------------- data quality
def imputed_share_by_district(df) -> pd.DataFrame:
    flags = [c for c in df.columns if c.endswith("_was_missing")]
    if not flags:
        return pd.DataFrame()
    out = (df.groupby("district")[flags].mean() * 100).round(1)
    out.columns = [c.replace("_was_missing", "") for c in out.columns]
    return out.reset_index()


# --------------------------------------------------------------------------- findings
def key_findings(df) -> list[str]:
    """Plain-language findings computed from the data, used by the report and dashboard."""
    f = []
    reg = regional_production(df)
    top, bottom = reg.iloc[0], reg.iloc[-1]
    gap = (top["total_qtl"] / bottom["total_qtl"] - 1) * 100
    f.append(f"{top['district']} has the highest production ({top['total_qtl']:,.0f} quintals, {top['share_pct']:.1f}% of the total) "
             f"and {bottom['district']} the lowest ({bottom['total_qtl']:,.0f}); the top district produces {gap:.0f}% more.")
    sh = seasonal_share(df)
    lead = sh.idxmax()
    f.append(f"{lead.capitalize()} season accounts for {sh.max():.0f}% of production, so output depends heavily on one season.")
    ps = price_summary(df)
    f.append(f"{ps.iloc[0]['crop_type'].capitalize()} earns the most per hectare (about INR {ps.iloc[0]['revenue_per_ha']:,.0f}), "
             f"while {ps.iloc[-1]['crop_type']} earns the least (about INR {ps.iloc[-1]['revenue_per_ha']:,.0f}).")
    cc = confounding_check(df)
    if cc["confounded"]:
        f.append(f"The pooled correlation between yield per hectare and price is {cc['pooled_r']}, but within each crop it never exceeds "
                 f"{cc['max_abs_within_r']} in absolute value: the pooled figure comes from crop mix, not a real link.")
    else:
        f.append(f"Correlation between yield per hectare and price is {cc['pooled_r']} overall and at most "
                 f"{cc['max_abs_within_r']} (absolute) within a single crop.")
    an = detect_anomalies(df)
    f.append(f"{int(an['anomaly'].sum())} of {len(df):,} records ({an['anomaly'].mean() * 100:.1f}%) were flagged as yield anomalies; "
             f"{int(an['both_signals'].sum())} were caught by both the IQR rule and the modified Z-score.")
    return f
