# =============================================================================
# File:         raster_to_tiff.py
# Project:      Master's thesis – Verification of Spectral, Radiometric, and Geometric Properties of DJI Mavic 3M, Matrice 4E, and Matrice 4T Devices
# Author:       Martin KRUPIČKA
# Date:         2026-02-04
# Version:      1.0.0
#
# Description:
#   ArcGIS Pro (ArcPy) script tool to clip a raster by polygons and export
#   each polygon as a GeoTIFF tile.
#
# Inputs:
#   - in_raster:    input raster dataset
#   - in_polygons:  polygon feature layer defining ROIs
#   - attr_field:   attribute field used to name output files
#   - out_folder:   output directory
#
# Outputs:
#   - Per-polygon GeoTIFFs named by the specified attribute field value
#
# Requirements:
#   - ArcGIS Pro / ArcPy
#
# Usage:
#   Run as an ArcGIS Pro Script Tool (parameters: in_raster, in_polygons,
#   attr_field, out_folder).
#
# =============================================================================

import arcpy
import os

# ArcPy environment settings
arcpy.env.overwriteOutput = True

# Script tool parameters
in_raster   = arcpy.GetParameterAsText(0)   # input raster dataset
in_polygons = arcpy.GetParameterAsText(1)   # polygon feature layer
attr_field  = arcpy.GetParameterAsText(2)   # attribute field used as output file prefix
out_folder  = arcpy.GetParameterAsText(3)   # output directory

# Create the output folder when it does not exist yet
if not os.path.exists(out_folder):
    os.makedirs(out_folder)

# Iterate over polygons and export one clipped TIFF per ROI
with arcpy.da.SearchCursor(in_polygons, ["SHAPE@", attr_field]) as cursor:
    for geom, prefix in cursor:
        # Create a temporary in-memory polygon feature for clipping
        temp_fc = os.path.join("in_memory", f"poly_{prefix}")
        arcpy.CopyFeatures_management(geom, temp_fc)

        # Build the output GeoTIFF path
        out_raster = os.path.join(out_folder, f"{prefix}.tif")

        # Clip the raster to the current polygon geometry
        arcpy.Clip_management(
            in_raster,
            "#",
            out_raster,
            temp_fc,
            "NoData",
            "ClippingGeometry",
            "MAINTAIN_EXTENT"
        )

        arcpy.AddMessage(f"Saved raster: {out_raster}")

        # Remove the temporary in-memory feature class
        arcpy.Delete_management(temp_fc)

arcpy.AddMessage("Done!")