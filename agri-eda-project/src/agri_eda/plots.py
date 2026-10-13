"""Static charts for the EDA report (matplotlib). One function per chart; each returns the saved path.

Design rules: one message per chart, fixed color per crop, a single y-axis, light gridlines,
legend always present when more than one series, and a palette checked for color-blind separation."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

from . import analysis as an

CROP_ORDER = ["wheat", "rice", "soybean", "maize", "chickpea"]
COLORS = dict(zip(CROP_ORDER, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]))
SEASON_COLORS = {"kharif": "#2a78d6", "rabi": "#eb6834", "zaid": "#1baf7a"}
SURFACE, INK, MUTED, GRID, BLUE = "#fcfcfb", "#0b0b0b", "#52514e", "#e1e0d9", "#2a78d6"


def _style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "text.color": INK, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.edgecolor": "#c3c2b7", "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.7, "axes.axisbelow": True,
        "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "legend.frameon": False,
    })


def _crops(df):
    present = set(df["crop_type"].unique())
    return [c for c in CROP_ORDER if c in present] + sorted(present - set(CROP_ORDER))


def _color(crop):
    return COLORS.get(crop, "#898781")


def _save(fig, out: Path, name: str) -> Path:
    fig.tight_layout()
    path = out / name
    fig.savefig(path, dpi=170)
    plt.close(fig)
    return path


def yield_distribution(df, out):
    crops = _crops(df)
    fig, axes = plt.subplots(1, len(crops), figsize=(11, 2.9), sharey=True, squeeze=False)
    for ax, crop in zip(axes[0], crops):
        ax.hist(df.loc[df.crop_type == crop, "yield_per_ha"], bins=18, color=_color(crop), edgecolor=SURFACE, linewidth=1.2)
        ax.set_title(crop.capitalize(), fontsize=10)
        ax.set_xlabel("Quintals / ha")
    axes[0][0].set_ylabel("Farms")
    fig.suptitle("Yield per hectare, one panel per crop", x=0.01, ha="left", fontsize=12, fontweight="bold")
    return _save(fig, out, "01_yield_distribution.png")


def regional_production(df, out):
    reg = an.regional_production(df).sort_values("total_qtl")
    vals = reg["total_qtl"] / 1000
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.barh(reg["district"], vals, color=BLUE, height=0.62)
    for y, v in enumerate(vals):
        ax.text(v + vals.max() * 0.01, y, f"{v:,.1f}k", va="center", color=MUTED, fontsize=9)
    ax.set_xlabel("Total production (thousand quintals)")
    ax.set_title("Regional production by district")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, vals.max() * 1.12)
    return _save(fig, out, "02_regional_production.png")


def seasonal_production(df, out):
    t = an.seasonal_production(df).pivot(index="season_year", columns="season", values="total_qtl").fillna(0) / 1000
    seasons = [s for s in an.SEASON_ORDER if s in t.columns]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    x, w = np.arange(len(t.index)), 0.8 / len(seasons)
    for i, s in enumerate(seasons):
        ax.bar(x + (i - (len(seasons) - 1) / 2) * w, t[s], width=w - 0.04, color=SEASON_COLORS[s], label=s.capitalize())
    ax.set_xticks(x, t.index.astype(int))
    ax.set_ylabel("Thousand quintals")
    ax.set_title("Seasonal production by year")
    ax.legend(ncol=3, loc="upper left", bbox_to_anchor=(0, -0.12))
    ax.grid(axis="x", visible=False)
    return _save(fig, out, "03_seasonal_production.png")


def price_trend(df, out):
    idx = an.price_index(df)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    for crop in [c for c in _crops(df) if c in idx.columns]:
        ax.plot(idx.index, idx[crop], color=_color(crop), lw=2, marker="o", ms=6, mec=SURFACE, mew=1.5, label=crop.capitalize())
    lo, hi = min(90, np.floor(idx.min().min() - 2)), max(110, np.ceil(idx.max().max() + 2))
    ax.set_ylim(lo, hi)
    ax.set_xticks(idx.index.astype(int))
    ax.set_ylabel("Price index (first year = 100)")
    ax.set_title("Market price trend by crop")
    ax.legend(ncol=5, loc="upper left", bbox_to_anchor=(0, -0.12), handlelength=1.2, columnspacing=1.2)
    return _save(fig, out, "04_price_trend.png")


def rainfall_vs_yield(df, out):
    fig, ax = plt.subplots(figsize=(7, 3.8))
    for crop in _crops(df):
        d = df[df.crop_type == crop]
        ax.scatter(d["rainfall_mm"], d["yield_per_ha"], s=14, alpha=0.55, color=_color(crop),
                   edgecolors=SURFACE, linewidths=0.4, label=crop.capitalize())
    ax.set_xlabel("Rainfall (mm)")
    ax.set_ylabel("Yield (quintals / ha)")
    ax.set_title("Rainfall vs yield per hectare")
    ax.legend(ncol=5, loc="upper left", bbox_to_anchor=(0, -0.16), markerscale=1.6, handletextpad=0.2, columnspacing=1.2)
    return _save(fig, out, "05_rainfall_vs_yield.png")


def correlation_heatmap(df, out):
    corr = an.pooled_correlation(df)
    cols = list(corr.columns)
    cmap = LinearSegmentedColormap.from_list("div", ["#eb6834", "#f0efec", "#2a78d6"])
    fig, ax = plt.subplots(figsize=(6.2, 5))
    ax.grid(False)
    im = ax.imshow(corr, cmap=cmap, vmin=-1, vmax=1)
    ax.set_xticks(range(len(cols)), cols, rotation=40, ha="right")
    ax.set_yticks(range(len(cols)), cols)
    for i in range(len(cols)):
        for j in range(len(cols)):
            ax.text(j, i, f"{corr.iat[i, j]:.2f}", ha="center", va="center", fontsize=8.5, color=INK)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title("Correlation matrix (all crops pooled)")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03).outline.set_visible(False)
    return _save(fig, out, "06_correlation_heatmap.png")


def within_crop_correlation(df, out, x="yield_per_ha", y="market_price"):
    """Pooled vs within-crop correlation: makes the confounding (Simpson's paradox) check visible."""
    cc = an.confounding_check(df, x, y)
    labels = ["All crops\npooled"] + [c.capitalize() for c in cc["within"]["crop_type"]]
    vals = [cc["pooled_r"]] + cc["within"]["r"].tolist()
    colors = ["#898781"] + [_color(c) for c in cc["within"]["crop_type"]]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar(labels, vals, color=colors, width=0.62)
    for i, v in enumerate(vals):
        ax.text(i, v + (0.03 if v >= 0 else -0.03), f"{v:.2f}", ha="center", va="bottom" if v >= 0 else "top", fontsize=9, color=INK)
    ax.axhline(0, color="#c3c2b7", lw=1)
    ax.set_ylim(-1.05, 1.05)
    ax.set_ylabel("Pearson r")
    ax.set_title(f"{x.replace('_', ' ').capitalize()} vs {y.replace('_', ' ')}: pooled vs within crop")
    ax.grid(axis="x", visible=False)
    return _save(fig, out, "07_pooled_vs_within_crop.png")


def anomaly_boxplot(df, out):
    crops = _crops(df)
    data = [df.loc[df.crop_type == c, "yield_per_ha_raw"] for c in crops]
    fig, ax = plt.subplots(figsize=(7, 3.8))
    bp = ax.boxplot(data, tick_labels=[c.capitalize() for c in crops], patch_artist=True, widths=0.5,
                    flierprops=dict(marker="o", markersize=4, markerfacecolor="#e34948", markeredgecolor=SURFACE, alpha=0.8),
                    medianprops=dict(color=INK, lw=1.5), whiskerprops=dict(color=MUTED), capprops=dict(color=MUTED))
    for patch, c in zip(bp["boxes"], crops):
        patch.set(facecolor=_color(c), edgecolor=SURFACE, alpha=0.9)
    if max(max(d) for d in data) / max(1e-9, min(min(d) for d in data)) > 50:
        ax.set_yscale("log")
        ax.set_ylabel("Raw yield per ha (log scale)")
    else:
        ax.set_ylabel("Raw yield per ha")
    ax.set_title("Anomaly screening: red dots lie beyond the IQR fences")
    ax.grid(axis="x", visible=False)
    return _save(fig, out, "08_anomaly_boxplot.png")


ALL = [yield_distribution, regional_production, seasonal_production, price_trend,
       rainfall_vs_yield, correlation_heatmap, within_crop_correlation, anomaly_boxplot]


def make_all(df, out_dir) -> list[Path]:
    _style()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    return [f(df, out) for f in ALL]
