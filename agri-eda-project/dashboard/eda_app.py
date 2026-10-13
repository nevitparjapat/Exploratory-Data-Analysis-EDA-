"""Point-and-click EDA dashboard.   Run with:  streamlit run dashboard/eda_app.py"""
import sys
import tempfile
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agri_eda import analysis as an  # noqa: E402
from agri_eda import plots  # noqa: E402
from agri_eda.report import build_report  # noqa: E402

SAMPLE = ROOT / "data" / "sample" / "agri_clean_sample.csv"
CROP_COLORS = alt.Scale(domain=plots.CROP_ORDER, range=[plots.COLORS[c] for c in plots.CROP_ORDER])
GREEN = "#2E7D32"

st.set_page_config(page_title="Agribusiness EDA Dashboard", page_icon="📊", layout="wide")
st.markdown("""
<style>
 .block-container {padding-top: 1.6rem;}
 div[data-testid="stMetric"] {background:#F1F8F2; border:1px solid #C8E6C9; padding:14px 16px; border-radius:12px;}
 div[data-testid="stMetric"] label {color:#2E7D32;}
 @media (prefers-color-scheme: dark) {
   div[data-testid="stMetric"] {background:#1B2A1D; border-color:#2E4A31;}
   div[data-testid="stMetric"] label {color:#81C784;}
 }
</style>""", unsafe_allow_html=True)

st.title("📊 Agribusiness EDA Dashboard")
st.caption("Explore regional production, seasons, prices, correlations and anomalies. Choose a data source and use the filters on the left.")

# ---------------------------------------------------------------- data source
with st.sidebar:
    st.header("1. Data")
    src = st.radio("Source", ["Bundled sample", "Upload cleaned CSV"], label_visibility="collapsed")
    upload = st.file_uploader("Cleaned CSV", type="csv") if src == "Upload cleaned CSV" else None
    if src == "Upload cleaned CSV":
        st.caption("Needs: " + ", ".join(an.REQUIRED))


@st.cache_data(show_spinner=False)
def _load(path_or_bytes, name):
    if isinstance(path_or_bytes, (str, Path)):
        return an.load_data(path_or_bytes)
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as t:
        t.write(path_or_bytes)
    return an.load_data(t.name)


try:
    if src == "Bundled sample":
        data = _load(str(SAMPLE), "sample")
    elif upload is not None:
        data = _load(upload.getvalue(), upload.name)
    else:
        st.info("👈 Upload a cleaned CSV, or switch to the bundled sample.")
        st.stop()
except ValueError as e:
    st.error(str(e))
    st.stop()

with st.sidebar:
    st.header("2. Filters")
    crops = st.multiselect("Crop", sorted(data["crop_type"].unique()), default=sorted(data["crop_type"].unique()))
    districts = st.multiselect("District", sorted(data["district"].unique()), default=sorted(data["district"].unique()))
    years = st.multiselect("Year", sorted(data["season_year"].unique()), default=sorted(data["season_year"].unique()))

df = an.apply_filters(data, crops, districts, years)
if df.empty:
    st.warning("No records match these filters.")
    st.stop()
if "synthetic" in str(SAMPLE.name) or src == "Bundled sample":
    st.caption("ℹ️ The bundled sample is synthetic: numbers demonstrate the method and are not real findings.")

# ---------------------------------------------------------------- KPIs
reg = an.regional_production(df)
sh = an.seasonal_share(df)
flagged = an.detect_anomalies(df)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Records", f"{len(df):,}")
c2.metric("Production (qtl)", f"{df['yield_qtl'].sum():,.0f}")
c3.metric("Median yield / ha", f"{df['yield_per_ha'].median():.1f}")
c4.metric("Top district", reg.iloc[0]["district"])
c5.metric("Anomalies flagged", f"{int(flagged['anomaly'].sum()):,}")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["💡 Key findings", "🗺 Regional & seasonal", "🌾 Yield", "🔗 Relationships", "⚠ Anomalies", "📄 Report"])

# ---------------------------------------------------------------- findings
with tab1:
    st.subheader("What the data says")
    for s in an.key_findings(df):
        st.markdown(f"- {s}")
    st.subheader("Price and profitability by crop")
    ps = an.price_summary(df)
    st.dataframe(ps, hide_index=True, width="stretch")
    bar = (alt.Chart(ps).mark_bar(cornerRadiusEnd=4)
           .encode(x=alt.X("crop_type:N", sort="-y", title="Crop"), y=alt.Y("revenue_per_ha:Q", title="Revenue per ha (INR)"),
                   color=alt.Color("crop_type:N", scale=CROP_COLORS, legend=None),
                   tooltip=["crop_type", alt.Tooltip("revenue_per_ha:Q", format=",.0f"), alt.Tooltip("price_cv_pct:Q", format=".1f")])
           .properties(height=280))
    st.altair_chart(bar, width="stretch")

# ---------------------------------------------------------------- regional & seasonal
with tab2:
    a, b = st.columns(2)
    with a:
        st.subheader("Production by district")
        ch = (alt.Chart(reg).mark_bar(color=plots.BLUE, cornerRadiusEnd=4)
              .encode(y=alt.Y("district:N", sort="-x", title=None), x=alt.X("total_qtl:Q", title="Quintals"),
                      tooltip=["district", alt.Tooltip("total_qtl:Q", format=",.0f"), alt.Tooltip("share_pct:Q", format=".1f"),
                               alt.Tooltip("median_yield_per_ha:Q", format=".1f")]).properties(height=300))
        st.altair_chart(ch, width="stretch")
    with b:
        st.subheader("Production by season and year")
        t = an.seasonal_production(df)
        t["season"] = t["season"].astype(str)
        ch2 = (alt.Chart(t).mark_bar()
               .encode(x=alt.X("season_year:O", title="Year"), y=alt.Y("total_qtl:Q", title="Quintals"), xOffset="season:N",
                       color=alt.Color("season:N", scale=alt.Scale(domain=list(plots.SEASON_COLORS), range=list(plots.SEASON_COLORS.values()))),
                       tooltip=["season_year", "season", alt.Tooltip("total_qtl:Q", format=",.0f"), alt.Tooltip("share_of_year_pct:Q", format=".1f")])
               .properties(height=300))
        st.altair_chart(ch2, width="stretch")
    st.subheader("Price index by crop (first year = 100)")
    pi = an.price_index(df).reset_index().melt("season_year", var_name="crop_type", value_name="index")
    ln = (alt.Chart(pi).mark_line(point=True, strokeWidth=2)
          .encode(x=alt.X("season_year:O", title="Year"), y=alt.Y("index:Q", scale=alt.Scale(domain=[90, 110]), title="Index"),
                  color=alt.Color("crop_type:N", scale=CROP_COLORS), tooltip=["crop_type", "season_year", "index"]).properties(height=260))
    st.altair_chart(ln, width="stretch")
    with st.expander("Do districts differ in yield within a crop? (Kruskal-Wallis, Bonferroni-adjusted)"):
        st.dataframe(an.district_difference_test(df), hide_index=True, width="stretch")

# ---------------------------------------------------------------- yield
with tab3:
    a, b = st.columns(2)
    with a:
        st.subheader("Yield per hectare by crop")
        bx = (alt.Chart(df).mark_boxplot(extent="min-max")
              .encode(x=alt.X("crop_type:N", title="Crop"), y=alt.Y("yield_per_ha:Q", title="Quintals / ha"),
                      color=alt.Color("crop_type:N", scale=CROP_COLORS, legend=None)).properties(height=320))
        st.altair_chart(bx, width="stretch")
    with b:
        st.subheader("Distribution")
        crop_pick = st.selectbox("Crop", sorted(df["crop_type"].unique()))
        hist = (alt.Chart(df[df.crop_type == crop_pick]).mark_bar(color=plots.COLORS.get(crop_pick, "#898781"))
                .encode(x=alt.X("yield_per_ha:Q", bin=alt.Bin(maxbins=25), title="Quintals / ha"), y=alt.Y("count()", title="Farms"))
                .properties(height=280))
        st.altair_chart(hist, width="stretch")
    st.subheader("Summary statistics")
    st.dataframe(an.yield_summary_by_crop(df), hide_index=True, width="stretch")

# ---------------------------------------------------------------- relationships
with tab4:
    st.subheader("Explore a relationship")
    nums = [c for c in an.NUMERIC_DRIVERS if c in df.columns]
    x_col, y_col = st.columns(2)
    x = x_col.selectbox("X variable", nums, index=nums.index("rainfall_mm"))
    y = y_col.selectbox("Y variable", nums, index=nums.index("yield_per_ha"))
    if x == y:
        st.info("Pick two different variables.")
    else:
        sc = (alt.Chart(df).mark_circle(size=40, opacity=0.5)
              .encode(x=alt.X(f"{x}:Q"), y=alt.Y(f"{y}:Q"), color=alt.Color("crop_type:N", scale=CROP_COLORS),
                      tooltip=["farm_id", "crop_type", x, y]).properties(height=340).interactive())
        st.altair_chart(sc, width="stretch")
        cc = an.confounding_check(df, x, y)
        m1, m2 = st.columns([1, 2])
        m1.metric("Pooled correlation (all crops)", f"{cc['pooled_r']:.2f}")
        m2.markdown("**Within each crop:**")
        m2.dataframe(cc["within"], hide_index=True, width="stretch")
        if cc["confounded"]:
            st.warning("The pooled correlation is strong but disappears inside each crop. It comes from the crop mix, "
                       "not from a real relationship (Simpson's paradox).")
        elif max(abs(cc["pooled_r"]), cc["max_abs_within_r"]) < 0.2:
            st.info("No meaningful linear relationship (|r| below 0.2). Check for curved or delayed effects before concluding anything.")
    with st.expander("Correlation matrix and redundancy (VIF)"):
        st.dataframe(an.pooled_correlation(df).round(2), width="stretch")
        st.dataframe(an.vif_table(df), hide_index=True, width="stretch")

# ---------------------------------------------------------------- anomalies
with tab5:
    st.subheader("Flagged yield anomalies")
    st.caption("Two signals per crop: IQR fences and modified Z-score (above 3.5). Records are flagged, never silently deleted.")
    st.dataframe(an.anomaly_summary(flagged), hide_index=True, width="stretch")
    only = flagged[flagged["anomaly"]].sort_values("mod_z", key=abs, ascending=False)
    cols = ["farm_id", "district", "crop_type", "season_year", "yield_per_ha_raw", "yield_per_ha", "mod_z", "both_signals"]
    st.dataframe(only[[c for c in cols if c in only.columns]], hide_index=True, width="stretch", height=300)
    st.download_button("⬇ Download flagged records (CSV)", only.to_csv(index=False).encode("utf-8"), "flagged_anomalies.csv", "text/csv")
    imp = an.imputed_share_by_district(df)
    if not imp.empty:
        st.subheader("Data quality: share of imputed values by district (%)")
        st.dataframe(imp, hide_index=True, width="stretch")

# ---------------------------------------------------------------- report
with tab6:
    st.subheader("Generate the full EDA report")
    st.write("Builds a Markdown report (with figures) from the currently filtered data.")
    if st.button("Generate report", type="primary"):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            plots.make_all(df, tmp / "figures")
            rp = build_report(df, tmp / "figures", tmp / "eda_report.md", source="dashboard selection")
            st.session_state["report_md"] = rp.read_text(encoding="utf-8")
    if "report_md" in st.session_state:
        st.download_button("⬇ Download report (Markdown)", st.session_state["report_md"].encode("utf-8"),
                           "eda_report.md", "text/markdown")
        st.caption("Figures are created by the command-line tool: run `agri-eda` to produce the report together with its images.")
        with st.expander("Preview", expanded=True):
            st.markdown(st.session_state["report_md"].replace("](figures/", "](#"))
