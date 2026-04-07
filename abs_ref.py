# =============================================================================
# File:         abs_ref.py
# Project:      Master's thesis – Verification of Spectral, Radiometric, and Geometric Properties of DJI Mavic 3M, Matrice 4E, and Matrice 4T Devices
# Author:       Martin KRUPIČKA
# Date:         2025-12-05
# Version:      1.0.0
#
# Description:
#   Batch correction of ASD field-spectrometer relative reflectance to
#   approximate absolute reflectance, using a Spectralon panel with
#   known reflectance.  All CSV files in the input directory are
#   processed automatically and results are written to an abs95_output
#   sub-folder together with a combined dataset.
#
# Inputs:
#   - INPUT_DIR: folder containing ASD output CSV files
#                Required columns: Wavelength, Reflectance, Source
#
# Outputs:
#   - Per-file corrected CSVs with suffix '_abs95.csv' (abs95_output/)
#   - all_corrected_data.csv – concatenation of all corrected files with a
#     'File' column indicating the source filename
#
# Requirements:
#   - Python >= 3.9
#   - pandas
#
# Usage:
#   1. Set INPUT_DIR to the folder containing your ASD CSV files.
#   2. Optionally set CLIP_TO_0_1 = True to clamp reflectance values to [0, 1].
#   3. Run: python ASD_folder_relative_to_abs95.py
#
# Notes:
#   The correction formula is: Reflectance_abs95 = Reflectance * 0.95
#   Delimiter detection supports comma, semicolon, and tab-separated files.
#   Semicolon-delimited files are read with decimal-comma handling.
#
# =============================================================================

import os
import sys
import pandas as pd

# --------------------------
# 1) Paths
# --------------------------
INPUT_DIR = r"D:/DP/250908_chomoutovska_bc_data/data_dplomk/ASD/asd_output_filtered"
OUT_DIR   = os.path.join(INPUT_DIR, "abs95_output")

os.makedirs(OUT_DIR, exist_ok=True)

# --------------------------
# 2) Settings
# --------------------------
PANEL_REFLECTANCE = 0.95    # reflectance of the reflectance panel used for calibration (change if different)
CLIP_TO_0_1       = False   # set to True if you want values clipped to 0-1 range

# --------------------------
# 3) Helper - delimiter detection
# --------------------------
def detect_delim(file_path: str) -> str:
    """Read up to 3 non-empty lines and pick the most frequent delimiter."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
        lines = []
        for line in fh:
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
            if len(lines) == 3:
                break

    if not lines:
        return ","

    line = lines[0]
    counts = {
        "comma":     line.count(","),
        "semicolon": line.count(";"),
        "tab":       line.count("\t"),
    }
    winner = max(counts, key=counts.get)
    return winner

DELIM_MAP = {
    "comma":     ",",
    "semicolon": ";",
    "tab":       "\t",
}

# --------------------------
# 4) Find files
# --------------------------
files = [
    os.path.join(INPUT_DIR, f)
    for f in os.listdir(INPUT_DIR)
    if f.lower().endswith(".csv") and os.path.isfile(os.path.join(INPUT_DIR, f))
]

if not files:
    sys.exit("No CSV files found in the input directory.")

# --------------------------
# 5) Processing function
# --------------------------
def process_asd_file(file_path: str) -> dict:
    """
    Reads one ASD CSV file, converts relative reflectance to an approximate
    absolute reflectance using the configured panel reflectance, and saves the
    corrected table to the output directory.

    Args:
        file_path (str): Path to the ASD CSV file to process.

    Returns:
        dict: Dictionary containing the corrected dataframe under
            ``corrected_data`` and the saved output path under ``out_csv``.
    """
    print(f"Processing: {os.path.basename(file_path)}")

    delim_name = detect_delim(file_path)
    sep        = DELIM_MAP.get(delim_name, ",")

    if delim_name == "semicolon":
        
        df = pd.read_csv(file_path, sep=sep, decimal=",")
    else:
        df = pd.read_csv(file_path, sep=sep)

    required_cols = {"Wavelength", "Reflectance", "Source"}
    missing_cols  = required_cols - set(df.columns)

    if missing_cols:
        raise ValueError(
            f"File {os.path.basename(file_path)} is missing required columns: "
            + ", ".join(sorted(missing_cols))
        )

    df["Reflectance_abs95"] = df["Reflectance"] * PANEL_REFLECTANCE

    if CLIP_TO_0_1:
        df["Reflectance_abs95"] = df["Reflectance_abs95"].clip(lower=0, upper=1)

    stem    = os.path.splitext(os.path.basename(file_path))[0]
    out_csv = os.path.join(OUT_DIR, f"{stem}_abs95.csv")

    df.to_csv(out_csv, index=False)

    return {"corrected_data": df, "out_csv": out_csv}

# --------------------------
# 6) Run batch
# --------------------------
results     = []
valid_files = []

for f in files:
    try:
        res = process_asd_file(f)
        results.append(res)
        valid_files.append(f)
    except Exception as e:
        print(f"ERROR in file {os.path.basename(f)}: {e}")

if not results:
    sys.exit("No files were processed successfully.")

# --------------------------
# 7) Optional: combined corrected dataset
# --------------------------
combined_frames = []
for i, res in enumerate(results):
    df_copy         = res["corrected_data"].copy()
    df_copy["File"] = os.path.basename(valid_files[i])
    combined_frames.append(df_copy)

combined_all = pd.concat(combined_frames, ignore_index=True)
combined_all.to_csv(os.path.join(OUT_DIR, "all_corrected_data.csv"), index=False)

# --------------------------
# 8) Done
# --------------------------
print("\nDone.")
print(f"Input directory:  {INPUT_DIR}")
print(f"Output directory: {OUT_DIR}")
print(f"Combined data:    {os.path.join(OUT_DIR, 'all_corrected_data.csv')}")