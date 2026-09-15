"""Generate Figure 1: schematic of the spatial relationship between F, S, I, OE, UE."""

import numpy as np
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from shapely.geometry import Point

CRS = "EPSG:32611"


def jittered_blob(center, rx, ry, seed, n=200, jitter=0.10):
    rng = np.random.default_rng(seed)
    theta = np.linspace(0, 2 * np.pi, n)
    r = 1 + rng.normal(0, jitter, n)
    x = center[0] + rx * r * np.cos(theta)
    y = center[1] + ry * r * np.sin(theta)
    return gpd.GeoSeries([Point(xi, yi) for xi, yi in zip(x, y)]).union_all().convex_hull


# Two overlapping, irregular "fire perimeters" - enough offset/size difference
# to show a clear I / OE / UE split, but with substantial overlap.
F_poly = jittered_blob(center=(0, 0), rx=1000, ry=780, seed=7)          # observed
S_poly = jittered_blob(center=(430, 260), rx=1150, ry=820, seed=11)     # simulated, overpredicts + drifts NE

I_poly = F_poly.intersection(S_poly)
OE_poly = S_poly.difference(F_poly)
UE_poly = F_poly.difference(S_poly)

fig, ax = plt.subplots(figsize=(7, 6))

gpd.GeoSeries(I_poly).plot(ax=ax, color="#2ca02c", alpha=0.75, zorder=2)
gpd.GeoSeries(OE_poly).plot(ax=ax, color="#d62728", alpha=0.55, zorder=2)
gpd.GeoSeries(UE_poly).plot(ax=ax, color="#1f77b4", alpha=0.55, zorder=2)

gpd.GeoSeries(F_poly).boundary.plot(ax=ax, color="black", linewidth=2.0, zorder=3)
gpd.GeoSeries(S_poly).boundary.plot(ax=ax, color="black", linewidth=2.0, linestyle="--", zorder=3)

# Region labels, placed at a guaranteed-interior point of each (possibly
# concave/crescent-shaped) region, with a white halo so they read on any fill.
label_style = dict(ha="center", va="center", fontweight="bold", zorder=4,
                    path_effects=[pe.withStroke(linewidth=3, foreground="white")])
rp_I, rp_OE, rp_UE = I_poly.representative_point(), OE_poly.representative_point(), UE_poly.representative_point()
ax.annotate("$I$", xy=(rp_I.x, rp_I.y), fontsize=20, color="#1b6b1b", **label_style)
ax.annotate("$OE$", xy=(rp_OE.x, rp_OE.y), fontsize=16, color="#a11d1d", **label_style)
ax.annotate("$UE$", xy=(rp_UE.x, rp_UE.y), fontsize=16, color="#0f4c8c", **label_style)

# F / S boundary labels with leader lines.
ax.annotate("$F$ (observed)", xy=(-560, 700), xytext=(-1350, 1150),
            fontsize=12, ha="left",
            arrowprops=dict(arrowstyle="-", color="black", lw=1))
ax.annotate("$S$ (simulated)", xy=(950, -260), xytext=(1150, -750),
            fontsize=12, ha="left",
            arrowprops=dict(arrowstyle="-", color="black", lw=1, linestyle="--"))

legend_elems = [
    plt.Line2D([0], [0], color="black", lw=2.0, label="$F$ boundary (observed fire)"),
    plt.Line2D([0], [0], color="black", lw=2.0, linestyle="--", label="$S$ boundary (simulated fire)"),
    plt.Rectangle((0, 0), 1, 1, fc="#2ca02c", alpha=0.75, label="$I$ — correctly predicted"),
    plt.Rectangle((0, 0), 1, 1, fc="#d62728", alpha=0.55, label="$OE$ — overpredicted (false alarm)"),
    plt.Rectangle((0, 0), 1, 1, fc="#1f77b4", alpha=0.55, label="$UE$ — underpredicted (missed)"),
]
ax.legend(handles=legend_elems, loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=9, frameon=False)

ax.set_title("Figure 1: Spatial relationship between observed ($F$) and\nsimulated ($S$) fire perimeters", fontsize=12)
ax.set_aspect("equal")
ax.axis("off")

fig.savefig("figure1_schematic.png", dpi=200, bbox_inches="tight")
print("Saved figure1_schematic.png")
