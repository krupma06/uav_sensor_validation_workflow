# =============================================================================
# File:         ASD_sorting_to_csv.py
# Project:      Master's thesis – Verification of Spectral, Radiometric, and Geometric Properties of DJI Mavic 3M, Matrice 4E, and Matrice 4T Devices
# Author:       Martin KRUPIČKA
# Date:         2026-02-04
# Version:      1.0.0
#
# Description:
#   Batch-process ASD spectrometer exports by grouping repeated measurements
#   per surface and exporting band-specific reflectance CSV files.
#
# Inputs:
#   - input_folder: directory containing .asd or .asd.txt files (tab-delimited, decimal comma supported)
#   - bands: wavelength ranges (nm) for g/r/re/nir (edit in script)
#   - group_size: number of repeated measurements per surface (default: 3)
#
# Outputs:
#   - CSV files per surface and band in output_folder/<band>/surface<id>_<band>.csv
#
# Requirements:
#   - Python >= 3.9
#   - pandas
#
# Usage:
#   Edit input_folder/output_folder in the script, then run: python ASD_sorting_to_csv.py
#
# Notes:
#   If filenames contain '_abs', only those files are used; otherwise all
#   detected files are processed.
#   Assumes the first two columns are wavelength and reflectance.
#
# =============================================================================

import pandas as pd
from pathlib import Path

# Input and output folders
input_folder = Path(r"C:\Users\Jarda\Desktop\asd_output")
output_folder = Path(r"C:\Users\Jarda\Desktop\as")
output_folder.mkdir(exist_ok=True)

# Spectral band ranges of Mavic 3M (nm) (change if different)
bands = {
    "nir": (860 - 26, 860 + 26),  # 834–886
    "re":  (730 - 16, 730 + 16),  # 714–746
    "r":   (650 - 16, 650 + 16),  # 634–666
    "g":   (560 - 16, 560 + 16),  # 544–576
}

# Find all files ending with .asd or .asd.txt
all_files = sorted(list(input_folder.glob("*.asd")) + list(input_folder.glob("*.asd.txt")))
print(f"Found {len(all_files)} files in {input_folder}")

# Prefer files already marked as absolute reflectance when available
abs_files = [f for f in all_files if "_abs" in f.stem.lower()]

if not abs_files:
    print("⚠️ No files with '_abs' found in the filename, processing all detected files.")
    abs_files = all_files

print(f"Processing {len(abs_files)} files.")

group_size = 3  # Repeated measurements (change if different)

for i in range(0, len(abs_files), group_size):
    group = abs_files[i:i + group_size]
    surface_id = i // group_size + 1
    print(f"➡️ Processing surface {surface_id}, files: {[f.name for f in group]}")

    all_values = []
    for file in group:
        try:
            df = pd.read_csv(file, sep="\t", decimal=",", engine="python")
            # If the file contains more columns, keep only wavelength and reflectance
            df = df.iloc[:, :2]
            df.columns = ["Wavelength", "Reflectance"]
            df["Source"] = file.stem  # Store source filename for traceability
            all_values.append(df)
        except Exception as e:
            print(f"❌ Error while reading {file.name}: {e}")

    if not all_values:
        continue

    # Merge repeated measurements vertically into one combined table
    combined = pd.concat(all_values, ignore_index=True)

    # Split reflectance values by spectral band and save outputs
    for band_name, (low, high) in bands.items():
        band_df = combined[
            (combined["Wavelength"] >= low) &
            (combined["Wavelength"] <= high)
        ]

        # Create one subfolder per spectral band
        band_folder = output_folder / band_name
        band_folder.mkdir(exist_ok=True)

        out_file = band_folder / f"surface{surface_id}_{band_name}.csv"
        band_df.to_csv(out_file, index=False)
        print(f"   ✅ Saved {out_file} ({len(band_df)} rows)")
