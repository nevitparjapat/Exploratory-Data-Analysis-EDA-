from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agri_eda import analysis as an
from agri_eda import plots
from agri_eda.report import build_report

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample" / "agri_clean_sample.csv"


@pytest.fixture(scope="module")
def df():
    return an.load_data(SAMPLE)


def make_simpson(n=300, seed=0):
    """Two crops: the high-yield crop has a low price, the low-yield crop a high price.
    Inside each crop, yield and price are unrelated -> pooled correlation is strongly negative."""
    rng = np.random.default_rng(seed)
    rows = []
    for crop, y0, p0 in [("rice", 50, 2000), ("soybean", 14, 4600)]:
        for _ in range(n):
            rows.append({"farm_id": "F", "district": "A", "crop_type": crop, "season": "kharif", "season_year": 2024,
                         "area_ha": 1.0, "yield_qtl": rng.normal(y0, 2), "rainfall_mm": 800.0, "soil_ph": 6.5,
                         "fertilizer_kg": 100.0, "market_price": rng.normal(p0, 50)})
    d = pd.DataFrame(rows)
    d["yield_per_ha"] = d["yield_qtl"] / d["area_ha"]
    return d


def test_load_data_requires_columns(tmp_path):
    bad = tmp_path / "bad.csv"
    pd.DataFrame({"farm_id": [1]}).to_csv(bad, index=False)
    with pytest.raises(ValueError, match="missing required columns"):
        an.load_data(bad)


def test_sample_loads(df):
    assert len(df) > 1000 and {"yield_per_ha", "yield_outlier_flag"} <= set(df.columns)


def test_regional_shares_sum_to_100(df):
    reg = an.regional_production(df)
    assert reg["share_pct"].sum() == pytest.approx(100, abs=0.1)
    assert reg["total_qtl"].is_monotonic_decreasing


def test_seasonal_shares_sum_to_100_each_year(df):
    t = an.seasonal_production(df)
    assert t.groupby("season_year")["share_of_year_pct"].sum().round(1).eq(100).all()


def test_price_summary_revenue(df):
    ps = an.price_summary(df)
    row = ps.iloc[0]
    assert row["revenue_per_ha"] == pytest.approx(row["mean_yield_per_ha"] * row["mean_price"], rel=1e-3)


def test_confounding_detected_on_simpson_data():
    cc = an.confounding_check(make_simpson())
    assert cc["pooled_r"] < -0.9
    assert cc["max_abs_within_r"] < 0.2
    assert cc["confounded"]


def test_no_confounding_when_relationship_is_real():
    rng = np.random.default_rng(1)
    d = make_simpson()
    d["market_price"] = 5000 - 20 * d["yield_per_ha"] + rng.normal(0, 5, len(d))  # real link inside every crop
    assert not an.confounding_check(d)["confounded"]


def test_vif_flags_redundant_variable():
    rng = np.random.default_rng(2)
    a = rng.normal(size=500)
    d = pd.DataFrame({"a": a, "b": a * 2 + rng.normal(0, 0.01, 500), "c": rng.normal(size=500)})
    v = an.vif_table(d, ["a", "b", "c"]).set_index("variable")["vif"]
    assert v["a"] > 100 and v["b"] > 100 and v["c"] < 2


def test_anomaly_detection_finds_injected_values():
    rng = np.random.default_rng(3)
    d = pd.DataFrame({"crop_type": ["wheat"] * 200, "yield_per_ha_raw": rng.normal(42, 3, 200)})
    d.loc[[5, 50], "yield_per_ha_raw"] = [4200.0, 0.1]
    out = an.detect_anomalies(d)
    assert out.loc[[5, 50], "anomaly"].all()
    assert out["anomaly"].sum() <= 8  # a few natural tail values at most


def test_anomaly_flags_are_per_crop():
    d = pd.DataFrame({"crop_type": ["a"] * 50 + ["b"] * 50,
                      "yield_per_ha_raw": list(np.linspace(10, 12, 50)) + list(np.linspace(100, 120, 50))})
    assert not an.detect_anomalies(d)["anomaly"].any()  # 110 is normal for crop b, even though far from crop a


def test_district_test_runs(df):
    kw = an.district_difference_test(df)
    assert {"p_value", "p_adjusted"} <= set(kw.columns)
    assert (kw["p_adjusted"] >= kw["p_value"]).all()


def test_key_findings_text(df):
    f = an.key_findings(df)
    assert len(f) == 5 and all(isinstance(s, str) and s for s in f)


def test_filters(df):
    sub = an.apply_filters(df, crops=["wheat"], years=[2024])
    assert set(sub["crop_type"]) == {"wheat"} and set(sub["season_year"]) == {2024}


def test_figures_and_report(df, tmp_path):
    figs = plots.make_all(df, tmp_path / "figures")
    assert len(figs) == 8 and all(f.exists() and f.stat().st_size > 5000 for f in figs)
    rep = build_report(df, tmp_path / "figures", tmp_path / "eda_report.md", source="sample")
    text = rep.read_text(encoding="utf-8")
    for heading in ["Executive summary", "Methodology", "Anomalies", "recommendations", "Limitations"]:
        assert heading.lower() in text.lower()
    assert "figures/01_yield_distribution.png" in text


def test_report_is_reproducible(df, tmp_path):
    a = build_report(df, tmp_path / "f1", tmp_path / "r1.md").read_text().split("\n", 3)[3]
    b = build_report(df, tmp_path / "f1", tmp_path / "r2.md").read_text().split("\n", 3)[3]
    assert a == b  # same data -> same report body (the date line is ignored)
