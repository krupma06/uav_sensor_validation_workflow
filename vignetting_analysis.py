# =============================================================================
# File:         vignetting_analysis.py
# Project:      Master's thesis – Verification of Spectral, Radiometric, and
#               Geometric Properties of DJI Mavic 3M, Matrice 4E, and
#               Matrice 4T Devices
# Author:       Martin KRUPIČKA
# Date:         2026-02-11
# Version:      1.0.0
#
# Description:
#   Script for vignetting analysis of camera images. Computes basic statistics
#   (min/max/diff) and extracts horizontal, vertical, and diagonal DN profiles
#   from a set of images. Non-TIFF files (JPG, PNG, DNG/RAW, …) are
#   first converted to grayscale TIFF; native TIFFs are profiled directly.
#
# Inputs:
#   - input_folder : directory containing .tif/.tiff/.jpg/.jpeg/.png
#                    and supported RAW files (.dng, .nef, .cr2, .cr3, .arw,.rw2, .orf, .raf)
#   - output_folder: directory for all outputs
#
# Outputs:
#   - gray/          : grayscale TIFF copies of non-TIFF source images
#   - summary.csv    : per-image min / max / diff statistics
#   - profiles_H.csv : horizontal DN profiles (+ MEDIAN row)
#   - profiles_V.csv : vertical DN profiles (+ MEDIAN row)
#   - profiles_D1.csv: main-diagonal DN profiles (+ MEDIAN row)
#   - profiles_D2.csv: anti-diagonal DN profiles (+ MEDIAN row)
#
# Requirements:
#   - Python 3.x
#   - Pillow  (pip install pillow)
#   - numpy   (pip install numpy)
#   - rawpy   (pip install rawpy)       ← required for DNG/RAW support
#
# Usage:
#   1. Set input_folder and output_folder below.
#   2. Run:  python vignetting_analysis.py
#
# Notes:
#   - H and V are extracted through the exact image centre as the central rowand column.
#   - D1 and D2 are sampled at regular intervals using bilinear interpolation.
#   - When images have different resolutions the profiles are padded with NaN
#     so that all rows share the same length; the MEDIAN row uses nanmedian.
#   - RAW files are converted from the visible RAW mosaic to a single-band
#     grayscale TIFF by averaging 2x2 Bayer cells after black-level
#     correction.
#
# =============================================================================

import os
import sys
import csv
import numpy as np
from PIL import Image
import rawpy

# ---------------------------
# User-defined paths
# ---------------------------
input_folder  = r"Put/Your/Input/Folder/Here" # <-- CHANGE THIS to your input folder path
output_folder = r"Put/Your/Output/Folder/Here" # <-- CHANGE THIS to your output folder path

# ---------------------------
# Folder validation
# ---------------------------
if not os.path.exists(input_folder):
    print(f"Error: input folder does not exist: {input_folder}")
    sys.exit(1)

os.makedirs(output_folder, exist_ok=True)
gray_folder = os.path.join(output_folder, "gray")
os.makedirs(gray_folder, exist_ok=True)

# ---------------------------
# Collect supported input images
# ---------------------------
raw_exts = ('.dng', '.nef', '.cr2', '.cr3', '.arw', '.rw2', '.orf', '.raf')
valid_exts = ('.tif', '.tiff', '.jpg', '.jpeg', '.png') + raw_exts

images = [
    os.path.join(input_folder, f)
    for f in sorted(os.listdir(input_folder))
    if f.lower().endswith(valid_exts)
]

if not images:
    print("No images found.")
    sys.exit(0)

print(f"Found {len(images)} image(s).")

summary  = []
profiles = {"H": [], "V": [], "D1": [], "D2": []}

# ---------------------------
# Helper functions
# ---------------------------

def load_as_gray_array(path):
    """
    Loads an image file and returns it as a 2-D grayscale raster array

    Supports both single-band and multi-band images. Native pixel values are
    preserved as much as possible and multi-band images are converted to
    grayscale using luminance weights or by taking the first available band

    Args:
        path (str): Path to the input image file

    Returns:
        numpy.ndarray: 2-D float array containing grayscale raster values
    """
    with Image.open(path) as img:
        arr = np.array(img)          # keep native dtype (uint8 or uint16)

        # Multi-band image (RGB, RGBA, …) → convert to luminance manually
        if arr.ndim == 3:
            if arr.shape[2] >= 3:
                # Standard luminance weights for sRGB
                arr = (0.2989 * arr[:, :, 0] +
                       0.5870 * arr[:, :, 1] +
                       0.1140 * arr[:, :, 2])
            else:
                arr = arr[:, :, 0].astype(float)

        return arr.astype(float)


def load_raw_as_gray_array(path):
    """
    Loads a RAW/DNG image file and returns it as a 2-D grayscale raster array

    RAW data are read directly from the visible sensor mosaic using rawpy.
    A black-level correction is applied when metadata are available and the
    mosaic is then reduced to a single-band grayscale raster by averaging
    2x2 Bayer cells.

    Args:
        path (str): Path to the input RAW image file

    Returns:
        numpy.ndarray: 2-D float array containing grayscale raster values
    """
    with rawpy.imread(path) as raw:
        arr = raw.raw_image_visible.astype(np.float32)
        black_levels = np.array(raw.black_level_per_channel, dtype=np.float32)

        if black_levels.size > 0:
            if black_levels.size >= 4:
                colors = raw.raw_colors_visible
                arr = arr - black_levels[colors]
            else:
                arr = arr - float(np.mean(black_levels))

        arr = np.clip(arr, 0, None)

        rows, cols = arr.shape
        rows2 = (rows // 2) * 2
        cols2 = (cols // 2) * 2
        arr = arr[:rows2, :cols2]

        # Convert Bayer mosaic to a single-band grayscale array
        arr = arr.reshape(rows2 // 2, 2, cols2 // 2, 2).mean(axis=(1, 3))

        return arr.astype(float)


def convert_to_gray_tiff(src, dst):
    """
    Converts a supported image file to a grayscale TIFF copy

    The function is intended for non-TIFF inputs such as JPG, PNG or
    DNG/RAW. Multi-band images are converted to grayscale and the output TIFF
    is saved while preserving the original bit depth where possible

    Args:
        src (str): Path to the source image file
        dst (str): Path where the grayscale TIFF will be saved

    Returns:
        str | None: Output TIFF path if conversion succeeds, otherwise None
    """
    try:
        ext = os.path.splitext(src)[1].lower()

        # RAW / DNG branch
        if ext in raw_exts:
            arr = load_raw_as_gray_array(src)
            arr = np.clip(np.rint(arr), 0, 65535).astype(np.uint16)
            gray = Image.fromarray(arr)
            gray.save(dst, format="TIFF")
            return dst

        # Standard image branch (JPG/PNG/HEIC/...)
        with Image.open(src) as img:
            arr = np.array(img)

            # Multi-band → luminance
            if arr.ndim == 3:
                if arr.shape[2] >= 3:
                    arr = (0.2989 * arr[:, :, 0] +
                           0.5870 * arr[:, :, 1] +
                           0.1140 * arr[:, :, 2])
                else:
                    arr = arr[:, :, 0]

                arr = (
                    arr.astype(np.uint16)
                    if img.mode in ("I;16", "I")
                    else arr.astype(np.uint8)
                )

            gray = Image.fromarray(arr)
            gray.save(dst, format="TIFF")
        return dst

    except Exception as e:
        print(f"  [ERROR] conversion failed for {src}: {e}")
        return None


def bilinear_sample(arr, x, y):
    """
    Samples a 2-D raster array at floating-point coordinates

    Bilinear interpolation is used so that profiles can follow arbitrary
    image lines rather than only integer-indexed rows, columns or diagonals.

    Args:
        arr (numpy.ndarray): Input 2-D raster array
        x (numpy.ndarray): Array of x coordinates (column positions)
        y (numpy.ndarray): Array of y coordinates (row positions)

    Returns:
        numpy.ndarray: Interpolated profile values
    """
    rows, cols = arr.shape

    x = np.clip(x, 0, cols - 1)
    y = np.clip(y, 0, rows - 1)

    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    x1 = np.clip(x0 + 1, 0, cols - 1)
    y1 = np.clip(y0 + 1, 0, rows - 1)

    dx = x - x0
    dy = y - y0

    top = (1.0 - dx) * arr[y0, x0] + dx * arr[y0, x1]
    bottom = (1.0 - dx) * arr[y1, x0] + dx * arr[y1, x1]

    return (1.0 - dy) * top + dy * bottom


def sample_line(arr, x0, y0, x1, y1, n_samples=None):
    """
    Samples a straight line in a 2-D raster array

    The line is parameterised from its start point to its end point and then
    sampled at regular intervals using bilinear interpolation.

    Args:
        arr (numpy.ndarray): Input 2-D raster array
        x0 (float): Start x coordinate
        y0 (float): Start y coordinate
        x1 (float): End x coordinate
        y1 (float): End y coordinate
        n_samples (int | None): Number of sample points. If None, the number
                                is derived from the Euclidean line length

    Returns:
        numpy.ndarray: Sampled profile values along the line
    """
    if n_samples is None:
        line_length = np.hypot(x1 - x0, y1 - y0)
        n_samples = int(np.ceil(line_length)) + 1

    x = np.linspace(x0, x1, n_samples)
    y = np.linspace(y0, y1, n_samples)
    return bilinear_sample(arr, x, y)


def extract_profiles(arr):
    """
    Extracts four central DN profiles from a 2-D raster array

    The extracted profiles correspond to the horizontal and vertical centre
    lines and to two diagonals passingthrough the image centre. Diagonal profiles are 
    sampled with bilinear interpolation so that they represent true image diagonals even for
    rectangular rasters.

    Args:
        arr (numpy.ndarray): Input 2-D array representing raster values

    Returns:
        tuple[numpy.ndarray, numpy.ndarray, numpy.ndarray, numpy.ndarray]:
            Horizontal profile, vertical profile, main diagonal profile and
            anti-diagonal profile
    """
    rows, cols = arr.shape

    h = arr[rows // 2, :].astype(float)
    v = arr[:, cols // 2].astype(float)

    d1 = sample_line(arr, 0.0, 0.0, cols - 1.0, rows - 1.0)
    d2 = sample_line(arr, cols - 1.0, 0.0, 0.0, rows - 1.0)

    return h, v, d1, d2


def save_summary(data, path):
    """
    Saves per-image summary statistics to a CSV file

    The output table contains one row per image with the minimum value,
    maximum value and their difference

    Args:
        data (list[tuple]): List of summary records to be written to the CSV
        path (str): Output path for the summary CSV file

    Returns:
        None
    """
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(["image", "min", "max", "diff"])
        w.writerows(data)


def save_profiles(profiles, folder):
    """
    Saves extracted DN profiles to CSV files by profile direction

    One CSV file is created for each profile type (H, V, D1, D2). Profiles
    are aligned to a common length by truncation or NaN padding, and an
    additional MEDIAN row is appended using nanmedian across all images

    Args:
        profiles (dict): Dictionary containing profile lists grouped by
                         direction
        folder (str): Output directory where the profile CSV files will be
                      saved

    Returns:
        None
    """
    for key, items in profiles.items():
        if not items:
            continue
        out_path = os.path.join(folder, f"profiles_{key}.csv")
        # Use the first profile's length as the reference column count
        length = len(items[0][1])
        with open(out_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(["image"] + [f"p{i}" for i in range(length)])

            stack = []
            for name, arr in items:
                # Align profile length: truncate if longer, pad with NaN if shorter
                if len(arr) >= length:
                    row = arr[:length].tolist()
                else:
                    row = arr.tolist() + [float('nan')] * (length - len(arr))
                w.writerow([name] + row)
                stack.append(np.array(row))

            # Median row – ignores NaN values introduced by padding
            median = np.nanmedian(np.vstack(stack), axis=0)
            w.writerow(["MEDIAN"] + median.tolist())

        print(f"  Saved: {out_path}")


# ---------------------------
# Main processing loop
# ---------------------------
for img_path in images:
    name    = os.path.splitext(os.path.basename(img_path))[0]
    ext     = os.path.splitext(img_path)[1].lower()
    is_tiff = ext in ('.tif', '.tiff')

    print(f"\nProcessing: {os.path.basename(img_path)}")

    # ── BRANCH A: TIFF – load directly and extract profiles ──────────────
    if is_tiff:
        try:
            arr = load_as_gray_array(img_path)
            print(f"  TIFF loaded as grayscale ({arr.shape[1]}x{arr.shape[0]} px)")
        except Exception as e:
            print(f"  [ERROR] failed to load TIFF {img_path}: {e}")
            continue

    # ── BRANCH B: other formats – convert to grayscale TIFF, then profile ─
    else:
        gray_tif = os.path.join(gray_folder, f"{name}_gray.tif")
        result   = convert_to_gray_tiff(img_path, gray_tif)
        if result is None:
            continue
        print(f"  Converted → {gray_tif}")
        try:
            arr = load_as_gray_array(gray_tif)
            print(f"  Grayscale TIFF loaded ({arr.shape[1]}x{arr.shape[0]} px)")
        except Exception as e:
            print(f"  [ERROR] failed to load converted TIFF: {e}")
            continue

    # ── Common: compute statistics and extract profiles ───────────────────
    mn, mx = np.min(arr), np.max(arr)
    summary.append((name, round(mn, 2), round(mx, 2), round(mx - mn, 2)))

    h, v, d1, d2 = extract_profiles(arr)
    profiles["H"].append((name, h))
    profiles["V"].append((name, v))
    profiles["D1"].append((name, d1))
    profiles["D2"].append((name, d2))

    print(f"  Profiles H/V/D1/D2 extracted.  min={mn:.1f}  max={mx:.1f}  diff={mx-mn:.1f}")

# ---------------------------
# Save results
# ---------------------------
summary_path = os.path.join(output_folder, "summary.csv")
save_summary(summary, summary_path)
print(f"\nSummary CSV: {summary_path}")

save_profiles(profiles, output_folder)

print("\nDone. All files processed successfully.")