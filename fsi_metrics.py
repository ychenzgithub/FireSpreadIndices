"""Fire Spread Indices (FSI): metrics for comparing simulated vs. observed fire perimeters.

Implements the metrics defined in FSI.md for both vector (polygon) and raster
(gridded binary/continuous) fire perimeter data:
  - Overlap:      IoU, Sorensen-Dice, SDI, ADI, Precision, Recall,
                   SDI_over/under, ADI_over/under, Expansion Ratio
  - Structural:   SSIM (raster only - requires a continuous or gridded field)
  - Boundary:     Hausdorff distance

Dependencies: numpy, pandas, geopandas, shapely>=2.0, rasterio, scipy, scikit-image

Usage:
    from fsi_metrics import evaluate_vector, evaluate_raster, evaluate_fire_perimeters

    # Vector perimeters (shapefile/GeoJSON/GeoPackage path, GeoDataFrame, or
    # shapely geometry) - areas computed analytically via polygon overlay.
    result = evaluate_vector("observed.geojson", "simulated.geojson")

    # Raster perimeters (GeoTIFF path or numpy array) - binary masks derived
    # by thresholding, sim is resampled onto the obs grid if they differ.
    result = evaluate_raster("observed.tif", "simulated.tif", ssim=True)

    # Or let the mode be inferred from the file extension / object type.
    result = evaluate_fire_perimeters("observed.shp", "simulated.shp")

    print(result)                 # formatted metrics
    result.values["IoU"]          # single metric, by name
    df = result.to_series()       # as a pandas Series, e.g. for batch runs

See example_fsi.py for a full worked example with synthetic data and plots.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import numpy as np
import geopandas as gpd
import rasterio
import rasterio.transform
from rasterio.warp import reproject, Resampling
from scipy.ndimage import binary_erosion
from scipy.spatial.distance import directed_hausdorff
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from skimage.metrics import structural_similarity as _ssim

VectorInput = Union[str, Path, gpd.GeoDataFrame, BaseGeometry]
RasterInput = Union[str, Path, np.ndarray]

VECTOR_EXTS = {".shp", ".geojson", ".json", ".gpkg", ".gml", ".kml"}
RASTER_EXTS = {".tif", ".tiff", ".img", ".asc", ".nc"}


# --------------------------------------------------------------------------- #
# Overlap metrics (shared by vector and raster paths)
# --------------------------------------------------------------------------- #

def overlap_metrics(I: float, OE: float, UE: float) -> dict:
    """Compute all area-based metrics in FSI.md sections 1-3 from I/OE/UE."""
    F = I + UE
    S = I + OE
    union = I + OE + UE
    return {
        "I": I, "OE": OE, "UE": UE, "F": F, "S": S,
        "IoU": I / union if union else np.nan,
        "Dice": 2 * I / (F + S) if (F + S) else np.nan,
        "SDI": (OE + UE) / F if F else np.nan,
        "ADI": (OE + UE) / I if I else np.nan,
        "Precision": I / S if S else np.nan,
        "Recall": I / F if F else np.nan,
        "SDI_over": OE / F if F else np.nan,
        "SDI_under": UE / F if F else np.nan,
        "ADI_over": OE / I if I else np.nan,
        "ADI_under": UE / I if I else np.nan,
        "ExpansionRatio": S / F if F else np.nan,
    }


@dataclass
class FireSpreadMetrics:
    values: dict
    geoms: Optional[dict] = None
    masks: Optional[dict] = None

    def to_series(self):
        import pandas as pd
        return pd.Series(self.values)

    def __repr__(self) -> str:
        rows = [
            f"{k:>15s}: {v:.4f}" if isinstance(v, float) else f"{k:>15s}: {v}"
            for k, v in self.values.items()
        ]
        return "\n".join(rows)


# --------------------------------------------------------------------------- #
# Vector path
# --------------------------------------------------------------------------- #

def _read_vector(obj: VectorInput) -> gpd.GeoDataFrame:
    if isinstance(obj, gpd.GeoDataFrame):
        return obj
    if isinstance(obj, BaseGeometry):
        return gpd.GeoDataFrame(geometry=[obj])
    return gpd.read_file(obj)


def _ensure_projected(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        raise ValueError("Vector input has no CRS defined; set one before comparing.")
    if gdf.crs.is_geographic:
        return gdf.to_crs(gdf.estimate_utm_crs())
    return gdf


def _extract_coords(geom: BaseGeometry) -> np.ndarray:
    if geom.is_empty:
        return np.empty((0, 2))
    if geom.geom_type == "MultiLineString":
        pts = [c for line in geom.geoms for c in line.coords]
    elif geom.geom_type == "GeometryCollection":
        pts = [c for g in geom.geoms for c in _extract_coords(g)]
    else:
        pts = list(geom.coords)
    return np.asarray(pts)


def vector_hausdorff(F_geom: BaseGeometry, S_geom: BaseGeometry,
                      densify_distance: Optional[float] = None) -> float:
    """Symmetric Hausdorff distance between two polygon boundaries, in CRS units."""
    f_b, s_b = F_geom.boundary, S_geom.boundary
    if densify_distance:
        f_b, s_b = f_b.segmentize(densify_distance), s_b.segmentize(densify_distance)
    f_pts, s_pts = _extract_coords(f_b), _extract_coords(s_b)
    if len(f_pts) == 0 or len(s_pts) == 0:
        return np.nan
    return max(directed_hausdorff(f_pts, s_pts)[0], directed_hausdorff(s_pts, f_pts)[0])


def evaluate_vector(obs: VectorInput, sim: VectorInput, target_crs=None,
                     hausdorff: bool = True, densify_distance: Optional[float] = None
                     ) -> FireSpreadMetrics:
    """Compare observed vs. simulated fire perimeters given as polygon(s).

    obs/sim: file path, GeoDataFrame, or shapely geometry.
    target_crs: projected CRS to compare in; auto-picks a UTM zone if omitted.
    densify_distance: max segment length (CRS units) used to densify boundaries
        before computing Hausdorff distance - needed when polygons have long,
        straight edges so the true closest-point distance isn't missed between
        vertices.
    """
    obs_gdf, sim_gdf = _read_vector(obs), _read_vector(sim)

    if target_crs is not None:
        obs_gdf, sim_gdf = obs_gdf.to_crs(target_crs), sim_gdf.to_crs(target_crs)
    else:
        obs_gdf = _ensure_projected(obs_gdf)
        sim_gdf = sim_gdf.to_crs(obs_gdf.crs) if sim_gdf.crs != obs_gdf.crs else sim_gdf

    F_geom = unary_union(obs_gdf.geometry).buffer(0)
    S_geom = unary_union(sim_gdf.geometry).buffer(0)
    I_geom = F_geom.intersection(S_geom)
    OE_geom = S_geom.difference(F_geom)
    UE_geom = F_geom.difference(S_geom)

    metrics = overlap_metrics(I_geom.area, OE_geom.area, UE_geom.area)
    if hausdorff:
        metrics["Hausdorff"] = vector_hausdorff(F_geom, S_geom, densify_distance)

    geoms = {"F": F_geom, "S": S_geom, "I": I_geom, "OE": OE_geom, "UE": UE_geom}
    return FireSpreadMetrics(metrics, geoms=geoms)


# --------------------------------------------------------------------------- #
# Raster path
# --------------------------------------------------------------------------- #

def _read_raster(obj: RasterInput, transform=None, crs=None, band: int = 1):
    if isinstance(obj, np.ndarray):
        return obj, transform, crs
    with rasterio.open(obj) as src:
        return src.read(band), src.transform, src.crs


def _align_to(mask: np.ndarray, src_transform, src_crs,
              dst_shape, dst_transform, dst_crs) -> np.ndarray:
    dst = np.zeros(dst_shape, dtype=np.uint8)
    reproject(
        source=mask.astype(np.uint8), destination=dst,
        src_transform=src_transform, src_crs=src_crs or dst_crs,
        dst_transform=dst_transform, dst_crs=dst_crs or src_crs,
        resampling=Resampling.nearest,
    )
    return dst.astype(bool)


def raster_hausdorff(obs_mask: np.ndarray, sim_mask: np.ndarray, transform) -> float:
    """Symmetric Hausdorff distance between raster fire-perimeter boundaries."""
    obs_b = obs_mask & ~binary_erosion(obs_mask)
    sim_b = sim_mask & ~binary_erosion(sim_mask)
    if not obs_b.any() or not sim_b.any():
        return np.nan
    obs_rows, obs_cols = np.nonzero(obs_b)
    sim_rows, sim_cols = np.nonzero(sim_b)
    obs_x, obs_y = rasterio.transform.xy(transform, obs_rows, obs_cols)
    sim_x, sim_y = rasterio.transform.xy(transform, sim_rows, sim_cols)
    obs_pts = np.column_stack([obs_x, obs_y])
    sim_pts = np.column_stack([sim_x, sim_y])
    return max(directed_hausdorff(obs_pts, sim_pts)[0], directed_hausdorff(sim_pts, obs_pts)[0])


def raster_ssim(obs_field: np.ndarray, sim_field: np.ndarray, data_range=None) -> float:
    """SSIM between two co-registered rasters (binary masks or continuous fields,
    e.g. rate-of-spread / arrival-time / burn-probability)."""
    if obs_field.shape != sim_field.shape:
        raise ValueError("SSIM requires obs and sim rasters on the same grid.")
    obs_f, sim_f = obs_field.astype(float), sim_field.astype(float)
    if data_range is None:
        data_range = max(obs_f.max(), sim_f.max()) - min(obs_f.min(), sim_f.min())
        data_range = data_range or 1.0
    return float(_ssim(obs_f, sim_f, data_range=data_range))


def evaluate_raster(obs: RasterInput, sim: RasterInput, threshold: float = 0,
                     obs_transform=None, sim_transform=None, obs_crs=None, sim_crs=None,
                     hausdorff: bool = True, ssim: bool = False) -> FireSpreadMetrics:
    """Compare observed vs. simulated fire perimeters given as rasters.

    obs/sim: GeoTIFF path or numpy array. Arrays are thresholded at `threshold`
        to obtain a binary burned/unburned mask (arr > threshold => burned).
    If obs/sim are on different grids, sim is reprojected/resampled (nearest)
    onto the obs grid before comparison - pass obs/sim_transform + obs/sim_crs
    when supplying bare arrays that don't already carry georeferencing.
    ssim: also computes SSIM directly on the raw (pre-threshold) input arrays,
        which is only meaningful if these carry a continuous field rather than
        a plain 0/1 mask.
    """
    obs_arr, o_tf, o_crs = _read_raster(obs, obs_transform, obs_crs)
    sim_arr, s_tf, s_crs = _read_raster(sim, sim_transform, sim_crs)

    obs_mask = obs_arr > threshold
    sim_mask = sim_arr > threshold

    if sim_mask.shape != obs_mask.shape or sim_arr.dtype != obs_arr.dtype or s_tf != o_tf:
        sim_mask = _align_to(sim_mask, s_tf, s_crs, obs_mask.shape, o_tf, o_crs)

    pixel_area = abs(o_tf.a * o_tf.e)
    I = np.logical_and(obs_mask, sim_mask).sum() * pixel_area
    OE = np.logical_and(~obs_mask, sim_mask).sum() * pixel_area
    UE = np.logical_and(obs_mask, ~sim_mask).sum() * pixel_area

    metrics = overlap_metrics(I, OE, UE)
    if hausdorff:
        metrics["Hausdorff"] = raster_hausdorff(obs_mask, sim_mask, o_tf)
    if ssim:
        sim_field = sim_arr if sim_arr.shape == obs_arr.shape else sim_mask.astype(float)
        metrics["SSIM"] = raster_ssim(obs_arr, sim_field)

    return FireSpreadMetrics(metrics, masks={"obs": obs_mask, "sim": sim_mask, "transform": o_tf})


# --------------------------------------------------------------------------- #
# Unified entry point
# --------------------------------------------------------------------------- #

def _infer_mode(obj) -> str:
    if isinstance(obj, (gpd.GeoDataFrame, BaseGeometry)):
        return "vector"
    if isinstance(obj, np.ndarray):
        return "raster"
    ext = Path(obj).suffix.lower()
    if ext in VECTOR_EXTS:
        return "vector"
    if ext in RASTER_EXTS:
        return "raster"
    raise ValueError(f"Cannot infer data type from extension '{ext}'; pass mode explicitly.")


def evaluate_fire_perimeters(obs, sim, mode: Optional[str] = None, **kwargs) -> FireSpreadMetrics:
    """Dispatch to evaluate_vector or evaluate_raster based on input type/extension."""
    mode = mode or _infer_mode(obs)
    if mode == "vector":
        return evaluate_vector(obs, sim, **kwargs)
    if mode == "raster":
        return evaluate_raster(obs, sim, **kwargs)
    raise ValueError(f"Unknown mode '{mode}'; expected 'vector' or 'raster'.")
