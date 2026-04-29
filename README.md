# DJI UAV Sensor Verification – Processing Scripts

This repository contains Python and R scripts used within the master’s thesis:

**Thesis title:** *Verification of Spectral, Radiometric, and Geometric Properties of DJI Mavic 3M, Matrice 4E, and Matrice 4T Devices*  
**Institution:** Palacký University, Department of Geoinformatics, Olomouc  
**Author:** Martin KRUPIČKA

The scripts cover:
- ASD spectrometer post-processing,
- approximate absolute reflectance correction of ASD outputs,
- multispectral radiometric calibration by the Empirical Line Method (ELM),
- DJI thermal R-JPEG → temperature TIFF conversion using DJI Thermal SDK,
- ArcGIS Pro / ArcPy ROI clipping,
- vignetting profile extraction from TIFF, common image formats, and RAW/DNG files,
- vignetting mask generation and correction of DJI Mavic 3M multispectral TIFF images,
- per-pixel median compositing of repeated rasters,
- R-based statistics and plotting for multispectral, thermal, and vignetting analyses.

---

## 1) Repository contents

The repository currently contains these scripts:

### Python
- `ASD_sorting_to_csv.py`
- `abs_ref.py`
- `radiometric_converter.py`
- `thermal_converter.py`
- `raster_to_tiff.py`
- `vignetting_analysis.py`
- `vignetting_correction.py`

### ArcGIS Pro toolbox
- `DP_Krupicka.atbx` *(contains the `RasterToTiff` script tool linked to `raster_to_tiff.py`)*

### R
- `multispec_r.R`
- `thermal_r.R`
- `median_from_rasters.R`
- `vignetting_r.R`

---

## 2) Requirements

### Python
- **Python 3.9+** (Windows recommended)
- Packages used across the scripts:
  - `numpy`
  - `pandas`
  - `rasterio`
  - `Pillow`
  - `tifffile`
  - `rawpy` *(required for RAW/DNG support in `vignetting_analysis.py`)*
  - `scipy` *(required for Gaussian smoothing in `vignetting_correction.py`, unless smoothing is disabled)*
  - `tkinter` *(usually bundled with standard Windows Python installs)*

Typical installation:

```bash
pip install numpy pandas rasterio pillow tifffile rawpy scipy
```

### DJI Thermal SDK
- `thermal_converter.py` requires **DJI Thermal SDK v1.8** and access to:
  - `dji_irp.exe`
- The script contains a placeholder Windows path that must be edited or selected in the GUI.

### ArcGIS Pro
- `raster_to_tiff.py` requires:
  - **ArcGIS Pro**
  - `arcpy`

### R
- **R 4.x**
- Packages used by the R scripts:
  - `terra`
  - `ggplot2`
  - `dplyr`
  - `stringr`
  - `readr`
  - `tidyr`
  - `zoo`
- `tools` is used in some scripts but is part of base R.

Typical installation:

```r
install.packages(c("terra", "ggplot2", "dplyr", "stringr", "readr", "tidyr", "zoo"))
```

---

## 3) Important notes before use

- Most scripts use **hard-coded paths** inside the source code.
  - These paths must be edited before running the scripts on another machine.
- Several scripts assume **specific filename conventions**.
  - These conventions are described in the per-script sections below.
- The scripts were developed for a **thesis-specific workflow**.
  - They are reusable, but they are not packaged as a general-purpose software library.
- Some workflows rely on **manually prepared folders** and **consistent naming of plots, bands, and heights**.
- Some of the R scripts generate plots with titles, subtitles, axis labels, and annotations written in Czech, as they were originally prepared for thesis outputs. When reusing these scripts, the text elements should be translated and adapted to the target dataset.
- Before the first run, it is recommended to open the selected script and check:
  - input paths,
  - output paths,
  - filename rules,
  - expected folder structure,
  - constants specific to the dataset.

### 3.1 Quick start

A practical way to start working with this repository is:

1. Download or clone the repository.
2. Install the required Python and R packages.
3. Open the script you want to use and edit the hard-coded paths.
4. Check that your filenames and folders match the expected conventions.
5. Run the selected workflow step-by-step rather than all scripts at once.

Typical first commands:

```bash
pip install numpy pandas rasterio pillow tifffile rawpy scipy
```

```r
install.packages(c("terra", "ggplot2", "dplyr", "stringr", "readr", "tidyr", "zoo"))
```

### 3.2 What this repository is and is not

This repository is best understood as a **thesis-specific collection of processing scripts**.  
It is suitable for:
- reproducing the described workflows,
- adapting the scripts for similar DJI / ASD / FLIR devices combination,
- inspecting the processing logic used in the thesis.

It is **not** intended to be:
- a fully packaged Python or R library,
- a universal GUI application,
- a plug-and-play workflow without path edits and data preparation.

---

## 4) Script overview

### 4.1 `ASD_sorting_to_csv.py` (Python)
**Purpose:**  
Batch-processes ASD spectrometer exports and saves band-filtered CSV files.

**What it does:**
- reads `.asd` or `.asd.txt` files from `input_folder`,
- prefers files whose names contain `_abs` if such files are available,
- groups repeated measurements by `group_size` (default = 3),
- filters wavelength ranges corresponding to DJI Mavic 3M bands,
- saves one CSV per surface and spectral band.

**Band ranges used in the script:**
- `G`: 544–576 nm
- `R`: 634–666 nm
- `RE`: 714–746 nm
- `NIR`: 834–886 nm

**Inputs:**
- `input_folder` with ASD export files,
- `group_size` specifying how many repeated measurements belong to one surface.

**Outputs:**
- `output_folder/g/surface<id>_g.csv`
- `output_folder/r/surface<id>_r.csv`
- `output_folder/re/surface<id>_re.csv`
- `output_folder/nir/surface<id>_nir.csv`

**Run:**
```bash
python ASD_sorting_to_csv.py
```

**Notes:**
- The script assumes the first two columns are wavelength and reflectance.
- Decimal comma in tab-delimited ASD exports is supported.

---

### 4.2 `abs_ref.py` (Python)
**Purpose:**  
Converts ASD relative reflectance CSV files to an **approximate absolute reflectance** scale using a known panel reflectance.

**What it does:**
- scans all CSV files in `INPUT_DIR`,
- detects the delimiter automatically (comma / semicolon / tab),
- checks for required columns `Wavelength`, `Reflectance`, and `Source`,
- computes:
  - `Reflectance_abs95 = Reflectance * PANEL_REFLECTANCE`,
- optionally clips corrected values to the interval `[0, 1]`,
- writes corrected per-file CSVs and one combined output table.

**Inputs:**
- folder with ASD CSV exports,
- required columns:
  - `Wavelength`
  - `Reflectance`
  - `Source`

**Outputs:**
- `abs95_output/<original_name>_abs95.csv`
- `abs95_output/all_corrected_data.csv`

**Run:**
```bash
python abs_ref.py
```

**Notes:**
- The default `PANEL_REFLECTANCE` is `0.95`.
- This is a simple multiplicative correction and should be interpreted as an approximation of absolute reflectance.

---

### 4.3 `radiometric_converter.py` (Python, Tkinter GUI)
**Purpose:**  
GUI tool for **multispectral radiometric calibration** by the **Empirical Line Method (ELM)**, with optional secondary scene normalisation.

**What it does:**
- loads close-up calibration panel images,
- reads a panel CSV with target reflectance values,
- computes panel DN statistics from a central crop,
- fits ELM coefficients per band:
  - `rho = a * DN + b`,
- if only one calibration panel is available, the intercept is forced to zero,
- applies calibration to a folder of multispectral GeoTIFFs,
- optionally performs scene normalisation using in-scene panel ROIs,
- supports ROI definition either from CSV or by interactive marking in the GUI,
- writes calibrated reflectance rasters.

**Inputs:**
- panel close-up folder,
- panel CSV with columns:
  - `filename`
  - `rho`
- image / ortho folder with GeoTIFFs to calibrate,
- optional scene ROI CSV with columns:
  - `filename,x0,y0,x1,y1,rho`
  - or ROIs can be marked interactively in the GUI.

**Filename expectation:**
- the band is parsed from the DJI multispectral token `_MS_`, for example:
  - `DJI_0001_MS_G.TIF`
  - `DJI_0001_MS_RE.TIF`

**Outputs:**
- calibrated reflectance rasters written to the output folder,
- filenames receive suffix `_refl`.

**Run:**
```bash
python radiometric_converter.py
```

**Notes:**
- Negative reflectance values can be clipped to 0.
- Values above 1 are kept.
- The script is intended for single-band multispectral GeoTIFF inputs.

---

### 4.4 `thermal_converter.py` (Python, Tkinter GUI)
**Purpose:**  
Batch conversion of DJI thermal **R-JPEG** images to single-band **temperature TIFFs (°C)** using **DJI Thermal SDK**.

**What it does:**
- calls `dji_irp.exe` for each input image,
- uses **manual environmental parameters** entered in the GUI,
- reads the temporary RAW output,
- detects RAW dimensions and data type from file size,
- converts values to °C,
- saves one float32 TIFF per input image,
- can delete temporary RAW files after successful conversion.

**Inputs:**
- folder with DJI thermal `.jpg` / `.jpeg` images,
- path to `dji_irp.exe`,
- manual parameters:
  - emissivity,
  - distance,
  - humidity,
  - ambient temperature,
  - reflected temperature.

**Outputs:**
- `<output_folder>/<image_name>.tiff`

**Run:**
```bash
python thermal_converter.py
```

**Notes:**
- The script was written around DJI Thermal SDK command-line usage.
- It requests float32 output from the SDK, but still detects the actual RAW type from file size.
- Temporary `.raw` files can be automatically removed.

---

### 4.5 `raster_to_tiff.py` (ArcGIS Pro / ArcPy)
**Purpose:**  
Clips a raster by polygons and exports one GeoTIFF per polygon.

**What it does:**
- reads an input raster,
- iterates over polygons from a feature layer,
- uses one attribute field as the output filename prefix,
- clips the raster to each polygon geometry,
- saves each clipped ROI as a separate TIFF.

**ArcGIS Script Tool parameters:**
1. `in_raster`
2. `in_polygons`
3. `attr_field`
4. `out_folder`

**Outputs:**
- `out_folder/<attribute_value>.tif`

**Run:**
- add the script as a **Script Tool** in ArcGIS Pro,
- provide the four parameters above.

**Notes:**
- Temporary in-memory polygon features are created during processing and deleted afterwards.

---

### 4.5b `DP_Krupicka.atbx` (ArcGIS Pro toolbox)
**Purpose:**  
Bundled **ArcGIS Pro toolbox** containing the `RasterToTiff` script tool based on `raster_to_tiff.py`.

**What it contains:**
- one script tool: `RasterToTiff`

**Tool parameters:**
1. `Input Raster`
2. `Input Polygons`
3. `Attribute Field`
4. `Output Folder`

**How to use it:**
- open ArcGIS Pro,
- add the provided `.atbx` toolbox,
- open the `RasterToTiff` tool,
- if needed, repair the script source so that it points to your local copy of `raster_to_tiff.py`,
- run the tool with the four user parameters.

**Notes:**
- The toolbox is a convenient packaged wrapper around `raster_to_tiff.py`.
- The included tool currently stores the original absolute script path from the author’s machine, so on another computer it may be necessary to relink the script file manually.
- Distributing the `.atbx` file together with `raster_to_tiff.py` is therefore recommended.

### 4.6 `vignetting_analysis.py` (Python)
**Purpose:**  
Extracts grayscale DN profiles from images for **vignetting analysis**.

**What it does:**
- reads supported image formats:
  - `.tif`, `.tiff`, `.jpg`, `.jpeg`, `.png`,
  - RAW formats: `.dng`,
- converts non-TIFF inputs to grayscale TIFF copies,
- computes per-image basic statistics:
  - minimum,
  - maximum,
  - difference,
- extracts four one-dimensional profiles:
  - `H` – horizontal centre line,
  - `V` – vertical centre line,
  - `D1` – main diagonal,
  - `D2` – anti-diagonal,
- pads profile tables with `NaN` where needed,
- computes a `MEDIAN` row across images,
- exports summary and profile CSV files.

**Inputs:**
- `input_folder` with supported image files,
- `output_folder`.

**Outputs:**
- `gray/` *(grayscale TIFF copies of non-TIFF inputs)*
- `summary.csv`
- `profiles_H.csv`
- `profiles_V.csv`
- `profiles_D1.csv`
- `profiles_D2.csv`

**Run:**
```bash
python vignetting_analysis.py
```

**Notes:**
- `rawpy` is required for RAW/DNG support.
- RAW files are converted from the visible sensor mosaic to a single-band grayscale TIFF by averaging 2×2 Bayer cells after black-level correction.

---

### 4.6b `vignetting_correction.py` (Python)
**Purpose:**  
Computes **vignetting correction masks** from homogeneous reference images and applies them to target images.

**What it does:**
- reads single-band TIFF images from a flat-field folder,
- detects DJI Mavic 3M spectral bands from filename tokens:
  - `_MS_G`, `_MS_R`, `_MS_RE`, `_MS_NIR`,
- normalises each flat-field image by the median value of its central crop,
- computes a pixel-wise median flat-field mask for each band,
- optionally smooths the mask using a Gaussian filter,
- saves both the vignetting mask and the corresponding correction factor,
- applies the correction to target images using:
  - `corrected = image / mask`,
- saves corrected TIFF images for further processing.

**Inputs:**
- `flat_field_folder` with homogeneous reference images,
- `image_folder` with images to be corrected,
- `output_folder` for masks and corrected images.

**Outputs:**
- `masks/vignetting_mask_<band>.tif`
- `masks/correction_factor_<band>.tif`
- `corrected/<original_name>_vigncorr.tif`

**Run:**
```bash
python vignetting_correction.py
```

**Notes:**
- The script is designed mainly for DJI Mavic 3M single-band multispectral TIFF images.
- If no band token is found in the filename, the image is grouped into band `ALL`.
- All flat-field images belonging to one band must have the same raster size.
- The safest output type before ELM calibration is `float32`, because corrected DN values are not clipped to the original integer range.
- The script does not apply an artificial maximum correction factor; invalid, zero, or negative mask values are replaced by `1.0` to avoid division by zero.

---

### 4.7 `multispec_r.R` (R)
**Purpose:**  
Loads UAV multispectral reflectance rasters for multiple flight altitudes, compares them with ASD reference data, computes accuracy metrics, and exports boxplots.

**What it does:**
- loads per-plot TIFFs for heights `40m`, `80m`, and `120m`,
- expects band subfolders:
  - `G`, `R`, `RE`, `NIR`,
- extracts all valid pixel values from each raster,
- merges repeated rasters belonging to the same plot,
- loads ASD CSV/TXT reference files recursively,
- prefers `Reflectance_abs95` when available, otherwise uses `Reflectance`,
- computes plot- and band-level summaries including median reflectance, SD, quartiles, and IQR,
- computes bias, absolute error, and squared error against ASD median values,
- computes overall `MAE_median`, `RMSE_median`, and `AvgBias_median` across heights,
- exports boxplots per plot and band.

**Expected UAV folder structure:**
```text
40m/
  G/
  R/
  RE/
  NIR/
80m/
  ...
120m/
  ...
```

**Plot ID rule:**
- the plot ID is taken as the first token before `_` in the TIFF filename,
- examples:
  - `ASF_1.tif` → plot `ASF`
  - `ASF_2.tif` → plot `ASF`

**ASD band detection in filenames:**
- band tokens can include forms such as:
  - `g`, `green`
  - `r`, `red`
  - `re`, `rededge`
  - `nir`

**Outputs:**
- `metrics_vs_ASD_per_height_median.csv`
- `metrics_vs_ASD_overall_median.csv`
- boxplots in `output_dir/<band>/`

**Run:**
```r
source("multispec_r.R")
```

**Notes:**
- Repeated rasters of the same plot are merged into one shared distribution.
- The ASD reference label used in plots is `0.25m (ASD)` by default.

---

### 4.8 `thermal_r.R` (R)
**Purpose:**  
Loads UAV thermal temperature rasters and FLIR reference rasters, computes plot-level thermal accuracy metrics, and exports boxplots.

**What it does:**
- loads TIFFs from folders representing:
  - `40m`
  - `80m`
  - `120m`
  - `FLIR_median`,
- extracts all valid raster values,
- derives plot IDs from filenames,
- optionally appends a single contact thermometer reference value for one selected plot,
- computes plot-level summaries including median temperature, SD, quartiles, and IQR,
- computes bias, absolute error, and squared error against FLIR median values,
- computes overall `MAE_median`, `RMSE_median`, and `AvgBias_median` across heights,
- generates per-plot boxplots.

**FLIR naming rule:**
- filenames beginning with `FLIR_` are parsed as:
  - `FLIR_<PLOT>_median.tif`

**Outputs:**
- `thermal_stats_formulas_median.csv`
- boxplots saved into `output_dir`

**Run:**
```r
source("thermal_r.R")
```

**Notes:**
- The FLIR plot label is set in the script as `1.5m (FLIR)`.
- The script currently appends one contact thermometer value for plot `VOD`.
- The contact thermometer label is set by `KONTAKTNI_LABEL`.

---

### 4.9 `median_from_rasters.R` (R)
**Purpose:**  
Computes a **per-pixel median composite** from repeated TIFF rasters sharing the same base filename.

**What it does:**
- scans the selected input folder for TIFF files,
- groups files by basename after removing Windows repeat suffixes such as:
  - `BET.tif`
  - `BET (2).tif`
  - `BET (3).tif`,
- stacks the rasters within each group,
- computes a per-pixel median,
- writes one output median raster for each group.

**Inputs:**
- `input_dir` containing repeated TIFF rasters.

**Outputs:**
- `<base_name>_median.tif`

**Run:**
```r
source("median_from_rasters.R")
```

**Notes:**
- All rasters within one group should have the same geometry.
- This is useful for reducing random noise across repeated acquisitions.

---

### 4.10 `vignetting_r.R` (R)
**Purpose:**  
Loads profile CSV files produced by `vignetting_analysis.py`, computes vignetting metrics from the **MEDIAN** profile, and exports plots.

**What it does:**
- reads `profiles_*.csv` files from `output_folder`,
- separates the `MEDIAN` row from individual image rows,
- computes metrics from the raw median profile,
- smooths the profile only for visualisation,
- exports plots for each profile direction,
- writes a summary metrics CSV.

**Computed metrics:**
- `center_value` = mean of the central 10 % of the profile,
- `edge_mean` = mean of the outer 5 % on each side,
- `vignetting_drop_abs` = `center_value - edge_mean`,
- `vignetting_drop_pct` = `(center_value - edge_mean) / center_value * 100`.

**Inputs:**
- folder containing:
  - `profiles_H.csv`
  - `profiles_V.csv`
  - `profiles_D1.csv`
  - `profiles_D2.csv`

**Outputs:**
- `profile_plot_<DIR>.png`
- `vignetting_metrics.csv`

**Run:**
```r
source("vignetting_r.R")
```

**Notes:**
- Metrics are computed from **non-smoothed** median values.
- Smoothing is used only for plot visualisation.
- Plot titles and subtitles are currently hard-coded in Czech and refer to DJI Mavic 3M / NIR unless edited.

---

## 5) Practical run examples

The scripts can be run individually depending on the workflow you need. In most cases, the safest approach is:
- edit paths and constants inside the script,
- test the script on a small subset of data,
- then run it on the full dataset.

### Python examples

```bash
python ASD_sorting_to_csv.py
python abs_ref.py
python vignetting_correction.py
python radiometric_converter.py
python thermal_converter.py
python vignetting_analysis.py
python vignetting_correction.py
```

### ArcGIS Pro / ArcPy

You can use the raster clipping workflow in two ways:
- add `raster_to_tiff.py` manually as an **ArcGIS Pro Script Tool**, or
- open the included `DP_Krupicka.atbx` toolbox and run the bundled `RasterToTiff` tool.

If the toolbox is opened on another machine, the script source may need to be relinked to the local `raster_to_tiff.py` file.

### R examples

The R scripts are easiest to run from **RStudio** after editing the working paths in the source code:

```r
source("multispec_r.R")
source("thermal_r.R")
source("median_from_rasters.R")
source("vignetting_r.R")
```

If preferred, the R scripts can also be run from the command line after adapting the file paths:

```bash
Rscript multispec_r.R
Rscript thermal_r.R
Rscript median_from_rasters.R
Rscript vignetting_r.R
```

---

## 6) Typical processing workflows

### A) Multispectral workflow
1. Prepare ASD outputs.
2. Filter ASD spectra by band using `ASD_sorting_to_csv.py`.
3. If needed, convert ASD relative reflectance to approximate absolute reflectance using `abs_ref.py`.
4. Compute masks and correct single-band TIFF images using `vignetting_correction.py` before ELM calibration.
5. Calibrate multispectral rasters to reflectance using `radiometric_converter.py`.
6. Clip calibrated rasters to ROI polygons using `raster_to_tiff.py` in ArcGIS Pro.
7. Compute statistics and generate boxplots using `multispec_r.R`.

### B) Thermal workflow
1. Convert DJI thermal R-JPEG images to temperature TIFFs using `thermal_converter.py`.
2. If repeated rasters should be combined, create median composites using `median_from_rasters.R`.
3. Clip rasters to ROI polygons if needed using `raster_to_tiff.py`.
4. Compute statistics and generate boxplots using `thermal_r.R`.

### C) Vignetting workflow
1. Prepare a folder with vignetting images.
2. Extract DN profiles using `vignetting_analysis.py`.
3. Compute vignetting metrics and export plots using `vignetting_r.R`.
4. Compute flat-field masks and apply them to target images using `vignetting_correction.py`.

---

## 7) Suggested folder organisation

A simple structure that works well with these scripts:

```text
project_root/
  data/
    asd/
    multispec/
      40m/
        G/
        R/
        RE/
        NIR/
      80m/
      120m/
    thermal/
      40m/
      80m/
      120m/
      FLIR_median/
    vignetting/
  outputs/
    multispec/
    thermal/
    vignetting/
  scripts/
    python/
    r/
```

This layout is only a suggestion. The scripts themselves work from whatever paths you define inside them.

---

## 8) Troubleshooting

### Python scripts do not run
- Check whether all required packages are installed.
- Verify that hard-coded paths were updated.

### `thermal_converter.py` fails
- Check that `dji_irp.exe` exists and matches your installed DJI Thermal SDK.
- Try running `dji_irp.exe` manually from the command line.

### `raster_to_tiff.py` or `DP_Krupicka.atbx` fails
- Run the workflow inside ArcGIS Pro with a valid ArcPy environment.
- Check that the polygon attribute field used for naming exists.
- If using the toolbox on another computer, verify that the `RasterToTiff` tool is correctly linked to the local `raster_to_tiff.py` script.

### R scripts report missing files or empty data
- Verify the folder structure and file naming.
- Check that plot IDs match between UAV and reference datasets.
- For multispectral analysis, check whether ASD filenames contain band tokens that can be parsed.

### `vignetting_analysis.py` fails on RAW / DNG files
- Install `rawpy`.
- Check whether the RAW format is one of the extensions handled in the script.

### `vignetting_correction.py` fails or produces no corrected images
- Check that `flat_field_folder`, `image_folder`, and `output_folder` point to valid folders.
- Verify that the input files are single-band TIFF images.
- If Gaussian smoothing is enabled, install `scipy` or set `gaussian_sigma = 0`.
- Check that flat-field and target images have the same raster size within each band.

---

## 9) Repository scope and reuse

These scripts were developed for academic research within the thesis stated above.  
If you reuse them in another project, it is recommended to:
- keep in mind that many parameters and paths are dataset-specific,
- validate the outputs on your own data,
- document any modifications you make,
- cite the thesis context where appropriate.
