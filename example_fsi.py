"""Example: score a simulated fire perimeter against an observed one, as vector and raster."""

import numpy as np
import geopandas as gpd
import matplotlib.pyplot as plt
from affine import Affine
from rasterio.features import rasterize
from shapely.geometry import Point

from fsi_metrics import evaluate_vector, evaluate_raster

CRS = "EPSG:32611"  # UTM 11N, meters - swap for whatever zone covers your fire

# --------------------------------------------------------------------------- #
# 1) Vector example: irregular "observed" perimeter vs. a shifted/over-grown
#    "simulated" one, each an ellipse with a jittered boundary.
# --------------------------------------------------------------------------- #

def jittered_ellipse(center, rx, ry, seed, n=200, jitter=0.06):
    rng = np.random.default_rng(seed)
    theta = np.linspace(0, 2 * np.pi, n)
    r = 1 + rng.normal(0, jitter, n)
    x = center[0] + rx * r * np.cos(theta)
    y = center[1] + ry * r * np.sin(theta)
    return gpd.GeoSeries([Point(xi, yi) for xi, yi in zip(x, y)]).union_all().convex_hull

obs_poly = jittered_ellipse(center=(500_000, 3_800_000), rx=1200, ry=900, seed=1)
sim_poly = jittered_ellipse(center=(500_300, 3_800_150), rx=1450, ry=950, seed=2)  # overpredicts, drifts NE

obs_gdf = gpd.GeoDataFrame(geometry=[obs_poly], crs=CRS)
sim_gdf = gpd.GeoDataFrame(geometry=[sim_poly], crs=CRS)

result_vec = evaluate_vector(obs_gdf, sim_gdf, densify_distance=30)
print("=== Vector metrics ===")
print(result_vec)

fig, ax = plt.subplots(figsize=(6, 6))
gpd.GeoSeries(result_vec.geoms["I"]).plot(ax=ax, color="green", label="I (correct)")
gpd.GeoSeries(result_vec.geoms["OE"]).plot(ax=ax, color="red", alpha=0.6, label="OE (overpredicted)")
gpd.GeoSeries(result_vec.geoms["UE"]).plot(ax=ax, color="blue", alpha=0.6, label="UE (underpredicted/missed)")
obs_gdf.boundary.plot(ax=ax, color="black", linewidth=1.5, label="Observed boundary")
sim_gdf.boundary.plot(ax=ax, color="black", linewidth=1.5, linestyle="--", label="Simulated boundary")
ax.set_title(f"IoU={result_vec.values['IoU']:.2f}  Dice={result_vec.values['Dice']:.2f}  "
             f"Hausdorff={result_vec.values['Hausdorff']:.0f} m")
ax.legend(loc="upper left", fontsize=8)
ax.set_aspect("equal")
fig.savefig("example_vector_comparison.png", dpi=150, bbox_inches="tight")
print("Saved example_vector_comparison.png\n")

# --------------------------------------------------------------------------- #
# 2) Raster example: rasterize the same two polygons onto a shared grid, plus
#    a continuous "rate of spread"-like field for the SSIM comparison.
# --------------------------------------------------------------------------- #

res = 15  # meters/pixel
minx, miny, maxx, maxy = gpd.GeoSeries([obs_poly, sim_poly]).total_bounds
minx, miny, maxx, maxy = minx - 300, miny - 300, maxx + 300, maxy + 300
width, height = int((maxx - minx) / res), int((maxy - miny) / res)
transform = Affine(res, 0, minx, 0, -res, maxy)

obs_mask = rasterize([(obs_poly, 1)], out_shape=(height, width), transform=transform, dtype="uint8")
sim_mask = rasterize([(sim_poly, 1)], out_shape=(height, width), transform=transform, dtype="uint8")

result_ras = evaluate_raster(
    obs_mask, sim_mask,
    obs_transform=transform, sim_transform=transform, obs_crs=CRS, sim_crs=CRS,
    threshold=0, ssim=True,
)
print("=== Raster metrics ===")
print(result_ras)

fig, ax = plt.subplots(figsize=(6, 6))
rgb = np.zeros((*obs_mask.shape, 3))
rgb[..., 0] = sim_mask & ~obs_mask  # red: overpredicted
rgb[..., 2] = obs_mask & ~sim_mask  # blue: missed
rgb[..., 1] = obs_mask & sim_mask   # green: correct
ax.imshow(rgb, extent=(minx, maxx, miny, maxy), origin="upper")
ax.set_title(f"IoU={result_ras.values['IoU']:.2f}  SSIM={result_ras.values['SSIM']:.2f}  "
             f"Hausdorff={result_ras.values['Hausdorff']:.0f} m")
fig.savefig("example_raster_comparison.png", dpi=150, bbox_inches="tight")
print("Saved example_raster_comparison.png")
