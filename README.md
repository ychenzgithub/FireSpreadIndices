# Fire Spread Indices (FSI)

A Python library and benchmark reference for evaluating wildfire spread simulations against observed fire perimeters. It supports both **vector** perimeters (Shapefile, GeoJSON, GeoPackage, `GeoDataFrame`) and **raster** grids (GeoTIFF, NumPy 2D arrays).

![Figure 1: Spatial relationship between observed (F) and simulated (S) fire perimeters](./figure1_schematic.png)

---

## 🌟 Features

- **Vector & Raster Support**: Calculate spatial evaluation metrics analytically using polygon overlays (`shapely` / `geopandas`) or numerically via binary/continuous raster grids (`rasterio` / `numpy`).
- **Comprehensive Spatial Metrics**:
  - **Overall Agreement**: IoU (Jaccard), Sørensen-Dice ($F_1$), Shape Deviation Index (SDI), Area Difference Index (ADI), Structural Similarity Index (SSIM).
  - **Overprediction / Specificity**: Precision (PPV), Partial SDI Over ($SDI_{over}$), Partial ADI Over ($ADI_{over}$), Fire Area / Expansion Ratio.
  - **Underprediction / Sensitivity**: Recall (TPR / Sensitivity), Partial SDI Under ($SDI_{under}$), Partial ADI Under ($ADI_{under}$).
  - **Boundary Distance**: Hausdorff distance ($d_H$) for worst-case perimeter mismatch.
- **Convenient Unified API**: Automatic modality inference (`evaluate_fire_perimeters`) with formatted terminal reports, dictionary access, and pandas Series conversion.

---

## 📐 Metrics Overview

The metrics follow standard notation comparing observed fire area $F$ and simulated fire area $S$:
* $F$: Reference / Observed fire area ($F = I + UE$)
* $S$: Simulated / Predicted fire area ($S = I + OE$)
* $I$: Intersection area (Correctly predicted burned area)
* $OE$: Overestimated area (False alarms / Overprediction)
* $UE$: Underestimated area (Missed burned area / Underprediction)

| Metric | Formula / Meaning | Key | Vector | Raster | Best Use Case |
|---|---|:---:|:---:|:---:|---|
| **Intersection over Union (IoU)** | $\frac{I}{S \cup F} = \frac{I}{I + OE + UE}$ | `IoU` | ✅ | ✅ | Standard benchmark for ranking spread models. |
| **Sørensen–Dice / $F_1$** | $\frac{2I}{F + S} = \frac{2I}{2I + OE + UE}$ | `Dice` | ✅ | ✅ | Multi-fire validation suites (less punishing on small fires). |
| **Shape Deviation Index (SDI)** | $\frac{OE + UE}{F}$ | `SDI` | ✅ | ✅ | Scale-independent total error normalized by observed fire size. |
| **Area Difference Index (ADI)** | $\frac{OE + UE}{I}$ | `ADI` | ✅ | ✅ | Stress test for catastrophic ignition/forcing failures ($I \to 0$). |
| **Precision / PPV** | $\frac{I}{S} = \frac{I}{I + OE}$ | `Precision` | ✅ | ✅ | Cost assessments of false alarms (evacuations, containment lines). |
| **Recall / TPR** | $\frac{I}{F} = \frac{I}{I + UE}$ | `Recall` | ✅ | ✅ | Life-safety early-warning validation (penalizes missed fire). |
| **Partial SDI (Over / Under)** | $\frac{OE}{F}$, $\frac{UE}{F}$ | `SDI_over`, `SDI_under` | ✅ | ✅ | Directional model bias across different fire sizes. |
| **Partial ADI (Over / Under)** | $\frac{OE}{I}$, $\frac{UE}{I}$ | `ADI_over`, `ADI_under` | ✅ | ✅ | Diagnostic for runaway growth or missed containment breach. |
| **Expansion Ratio** | $\frac{S}{F}$ | `ExpansionRatio` | ✅ | ✅ | Macro-scale burned-area sanity check (e.g. seasonal budgets). |
| **Hausdorff Distance** | $\max(d(S \to F), d(F \to S))$ | `Hausdorff` | ✅ | ✅ | Worst-case operational boundary error (front placement). |
| **SSIM** | Continuous field similarity | `SSIM` | ❌ | ✅ | Continuous raster fields (arrival-time isochrones, ROS grids). |

For detailed mathematical formulations, theoretical motivations, and metric discussions, see [FSI.md](./FSI.md).

---

## 🚀 Installation

Ensure you have Python 3.9+ installed. Install the required spatial and scientific libraries:

```bash
pip install numpy pandas geopandas shapely rasterio scipy scikit-image matplotlib
```

---

## 💻 Quick Start

### 1. Unified Interface

```python
from fsi_metrics import evaluate_fire_perimeters

# Automatically infers vector vs. raster based on file path or object type
result = evaluate_fire_perimeters("observed.geojson", "simulated.geojson")

# Print formatted summary table
print(result)

# Access individual metrics
print(f"IoU: {result.values['IoU']:.3f}")
print(f"Hausdorff distance: {result.values['Hausdorff']:.1f} m")

# Export as a pandas Series (e.g., for multi-fire batch runs)
series = result.to_series()
```

### 2. Vector Evaluation

```python
import geopandas as gpd
from fsi_metrics import evaluate_vector

obs_gdf = gpd.read_file("observed_perimeter.shp")
sim_gdf = gpd.read_file("simulated_perimeter.shp")

# densify_distance (meters) samples boundary coordinates for accurate Hausdorff distance calculation
result = evaluate_vector(obs_gdf, sim_gdf, densify_distance=25.0)

# Decomposed geometry components are available for plotting
# result.geoms contains: "I", "OE", "UE", "F", "S"
```

### 3. Raster Evaluation

```python
from fsi_metrics import evaluate_raster

# Binary or continuous rasters (e.g., GeoTIFF)
result = evaluate_raster("observed_arrival_time.tif", "simulated_arrival_time.tif", ssim=True)
print(f"SSIM: {result.values['SSIM']:.3f}")
```

---

## 📊 Visual Examples

Run [`example_fsi.py`](./example_fsi.py) to generate synthetic comparisons for vector and raster evaluations:

```bash
python example_fsi.py
```

### Vector Perimeter Comparison
Decomposition into Intersection ($I$, green), Overestimated ($OE$, red), and Underestimated ($UE$, blue):

![Vector Comparison](./example_vector_comparison.png)

### Continuous Raster Field Comparison (SSIM & Differences)
Continuous arrival-time / rate-of-spread evaluation and pixel classification:

![Raster Comparison](./example_raster_comparison.png)

---

## 📁 Repository Structure

```text
.
├── FSI.md                         # Detailed metric formulas, literature context, and guidelines
├── README.md                      # Project overview and quickstart documentation
├── fsi_metrics.py                 # Core evaluation library (vector & raster metrics)
├── example_fsi.py                 # Example script evaluating synthetic fire perimeters
├── figure1_schematic.py           # Script generating the schematic diagram
├── figure1_schematic.png          # Schematic figure of spatial metric definitions
├── example_vector_comparison.png  # Sample visualization of vector metric components
└── example_raster_comparison.png  # Sample visualization of raster metric evaluation
```

---

## 📄 License

MIT License. Feel free to use and adapt in your wildfire modeling and benchmarking pipelines.
