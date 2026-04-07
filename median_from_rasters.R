# =============================================================================
# File:         median_from_rasters.R
# Project:      Master's thesis – Verification of Spectral, Radiometric, and
#               Geometric Properties of DJI Mavic 3M, Matrice 4E, and
#               Matrice 4T Devices
# Author:       Martin KRUPIČKA
# Date:         2026-02-04
# Version:      1.0.0
#
# Description:
#   Load repeated TIFF rasters from a selected folder, group files with the
#   same base name, compute a per-pixel median composite for each group, and
#   export the result as a new GeoTIFF with suffix "_median.tif".
#
# Inputs:
#   - input_dir: directory containing repeated TIFF rasters
#   - Naming convention:
#       * repeated files follow Windows-style suffixing, for example
#         "BET.tif", "BET (2).tif", "BET (3).tif"
#
# Outputs:
#   - <base_name>_median.tif saved into input_dir
#
# Dependencies:
#   - terra
#   - tools (base R)
#
# Run:
#   Open in RStudio, set the path in 'input_dir', and run the script.
#
# Notes:
#   - Input rasters within each group should have the same geometry
#     (extent, resolution and number of rows/columns).
#   - The median is computed per pixel across all available repeated
#     acquisitions in the group.
#   - The median composite helps reduce the influence of random noise and
#     occasional outlier pixel values.
#
# =============================================================================

library(terra)

# Set the path to the input folder
input_dir <- "D:/DP/250908_chomoutovska_bc_data/260224_data_morava/260224_data_morava/output/dji/mediany/10"
setwd(input_dir)

# Find all TIFF files in the input directory
tiffs <- list.files(pattern = "\\.tif$", full.names = TRUE)

# Derive base names by removing repeat suffixes such as " (2)" or " (3)"
base_names <- gsub(" \\(\\d+\\)", "", basename(tiffs))
unique_names <- unique(base_names)

# Process each group of repeated rasters separately
for (name in unique_names) {
  files_group <- tiffs[base_names == name]

  # Load all rasters from the current group
  rasters <- rast(files_group)

  # Compute the per-pixel median across the raster stack
  r_median <- app(rasters, median, na.rm = TRUE)

  # Build the output filename with suffix "_median.tif"
  output_name <- file.path(
    input_dir,
    paste0(tools::file_path_sans_ext(name), "_median.tif")
  )

  # Save the median raster to disk
  writeRaster(r_median, output_name, overwrite = TRUE)

  # Print progress information to the console
  cat("Processed:", name, "→", output_name, "\n")
}