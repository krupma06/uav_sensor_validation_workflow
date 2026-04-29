# =============================================================================
# File:         vignetting_correction.py
# Project:      Master's thesis – Verification of Spectral, Radiometric, and
#               Geometric Properties of DJI Mavic 3M, Matrice 4E, and Matrice 4T
# Author:       Martin KRUPIČKA
# Date:         2026-04-24
# Version:      1.1.0
#
# Description:
#   Computes vignetting correction masks from homogeneous reference images and
#   applies them to another set of input images. The workflow is intended mainly
#   for DJI Mavic 3M multispectral single-band TIFF images before ELM calibration.
#
#   The vignetting mask is derived as a normalized illumination field.
#   Each flat-field image is first normalized by the median value of its central
#   image crop. Then a pixel-wise median is computed from all normalized
#   flat-field images belonging to the same spectral band.
#
#   The resulting mask is finally normalized again by the median value of its
#   central image crop:
#
#       mask = flat_field_normalized / central_reference_value
#
#   Therefore, values near the image centre are close to 1.0 and darker image
#   edges usually have values below 1.0. The corrected image is computed as:
#
#       corrected = image / mask
#
#   This increases DN values in darker peripheral parts of the image.
#
# Inputs:
#   - flat_field_folder : folder with homogeneous images used to compute masks
#   - image_folder      : folder with images to be corrected
#   - output_folder     : output folder for masks and corrected images
#
# Outputs:
#   - masks/vignetting_mask_<band>.tif
#   - masks/correction_factor_<band>.tif
#   - corrected/<original_name>_vigncorr.tif
#
# Requirements:
#   pip install numpy rasterio scipy
#
# Notes:
#   - The script is designed mainly for single-band TIFF files.
#   - Band is detected from DJI-like filenames containing:
#       _MS_G, _MS_R, _MS_RE, _MS_NIR
#   - If no band token is found, images are grouped into band "ALL".
#   - All flat-field images belonging to one band must have the same raster size.
#   - No artificial maximum correction factor is applied. The full mask-derived
#     correction is used, except for invalid or zero mask values, which are
#     replaced by 1.0 to avoid division by zero.
# =============================================================================

import os
import re
import sys
from pathlib import Path

import numpy as np
import rasterio

try:
    from scipy.ndimage import gaussian_filter
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


# =============================================================================
# USER SETTINGS
# =============================================================================

flat_field_folder = r"Put/Your/Flat-Field/Folder/Here" # <-- CHANGE THIS to your flat-field images folder path
image_folder = r"Put/Your/Image/Folder/Here" # <-- CHANGE THIS to your image folder path
output_folder = r"Put/Your/Output/Folder/Here" # <-- CHANGE THIS to your output folder path

# Central crop used for normalization.
# 0.10 means central 10 % of image width and height.
center_crop_fraction = 0.10

# Gaussian smoothing of the mask.
# Recommended because the flat-field image can contain local texture/noise.
# Set to 0 to disable smoothing.
gaussian_sigma = 35

# Output type:
# - "float32" is safest before ELM because no corrected DN information is lost.
# - "uint16" can be used if the next workflow requires integer TIFFs.
output_dtype = "float32"

# Supported raster formats.
valid_exts = (".tif", ".tiff")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def find_images(folder):
    """Return sorted list of supported image paths in a folder."""
    folder = Path(folder)
    return sorted([
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in valid_exts
    ])


def detect_band(path):
    """
    Detect DJI Mavic 3M band from filename.

    Supported examples:
        DJI_0001_MS_G.TIF
        DJI_0001_MS_R.TIF
        DJI_0001_MS_RE.TIF
        DJI_0001_MS_NIR.TIF

    Returns:
        str: G, R, RE, NIR, or ALL
    """
    name = path.name.upper()

    patterns = {
        "NIR": r"(^|_)MS_NIR($|_|\.)",
        "RE":  r"(^|_)MS_RE($|_|\.)",
        "G":   r"(^|_)MS_G($|_|\.)",
        "R":   r"(^|_)MS_R($|_|\.)",
    }

    for band, pattern in patterns.items():
        if re.search(pattern, name):
            return band

    return "ALL"


def group_by_band(paths):
    """Group image paths by detected band."""
    groups = {}

    for p in paths:
        band = detect_band(p)
        groups.setdefault(band, []).append(p)

    return groups


def read_single_band(path):
    """
    Read first raster band as float32 array and return array + raster profile.
    """
    with rasterio.open(path) as src:
        arr = src.read(1).astype(np.float32)
        profile = src.profile.copy()

        nodata = src.nodata
        if nodata is not None:
            arr = np.where(arr == nodata, np.nan, arr)

    return arr, profile


def central_crop_values(arr, fraction):
    """
    Extract values from central image crop.

    Args:
        arr (np.ndarray): 2-D image array.
        fraction (float): fraction of width/height used for crop.

    Returns:
        np.ndarray: central crop values.
    """
    rows, cols = arr.shape

    crop_h = max(1, int(rows * fraction))
    crop_w = max(1, int(cols * fraction))

    y0 = rows // 2 - crop_h // 2
    y1 = y0 + crop_h
    x0 = cols // 2 - crop_w // 2
    x1 = x0 + crop_w

    crop = arr[y0:y1, x0:x1]
    crop = crop[np.isfinite(crop)]

    if crop.size == 0:
        raise ValueError("Central crop contains no valid values.")

    return crop


def sanitize_mask(mask):
    """
    Replace invalid mask values with 1.0.

    A mask value of 1.0 means no correction. This is used only for invalid,
    zero or negative mask values, because these cannot be safely used for
    division.
    """
    mask = np.where(np.isfinite(mask), mask, 1.0)
    mask = np.where(mask <= 0, 1.0, mask)

    return mask.astype(np.float32)


def compute_band_mask(flat_paths, band):
    """
    Compute normalized vignetting mask for one band.

    Processing:
        1. Read all flat-field images.
        2. Normalize each flat-field image by the median value of its central crop.
        3. Stack normalized flat-field images.
        4. Compute pixel-wise median mask.
        5. Normalize final mask by the median value of its central crop.
        6. Optionally smooth the mask.
        7. Compute correction factor as 1 / mask.

    Returns:
        tuple[np.ndarray, np.ndarray, dict]:
            mask, correction_factor, reference raster profile
    """
    arrays = []
    reference_shape = None
    reference_profile = None
    center_values_per_image = []

    print(f"\nComputing mask for band: {band}")
    print(f"Flat-field images: {len(flat_paths)}")

    for path in flat_paths:
        arr, profile = read_single_band(path)

        if reference_shape is None:
            reference_shape = arr.shape
            reference_profile = profile
        elif arr.shape != reference_shape:
            raise ValueError(
                f"Different image size in band {band}: {path.name} has {arr.shape}, "
                f"expected {reference_shape}."
            )

        central_values = central_crop_values(arr, center_crop_fraction)
        central_reference_single = float(np.nanmedian(central_values))

        if not np.isfinite(central_reference_single) or central_reference_single <= 0:
            raise ValueError(
                f"Invalid central reference value in {path.name}: "
                f"{central_reference_single}"
            )

        # Normalize each flat-field image independently.
        # This reduces the influence of different overall brightness/exposure
        # between individual reference images.
        arr_normalized = arr / central_reference_single
        arrays.append(arr_normalized.astype(np.float32))
        center_values_per_image.append(central_reference_single)

        print(f"  loaded: {path.name}, center DN: {central_reference_single:.3f}")

    stack = np.stack(arrays, axis=0)

    # Pixel-wise median is more robust than mean if one flat-field image
    # contains local artefacts.
    mask = np.nanmedian(stack, axis=0).astype(np.float32)

    # Replace only invalid values before smoothing to prevent NaN propagation.
    mask = sanitize_mask(mask)

    # Re-normalize final mask so that the central area is close to 1.0.
    central_values = central_crop_values(mask, center_crop_fraction)
    central_reference = float(np.nanmedian(central_values))

    if not np.isfinite(central_reference) or central_reference <= 0:
        raise ValueError(
            f"Invalid final central reference value for band {band}: "
            f"{central_reference}"
        )

    mask = mask / central_reference
    mask = sanitize_mask(mask)

    # Smooth mask to suppress texture/noise of the photographed flat surface.
    if gaussian_sigma > 0:
        if not SCIPY_AVAILABLE:
            raise ImportError(
                "scipy is required for gaussian smoothing. "
                "Install it using: pip install scipy "
                "or set gaussian_sigma = 0."
            )

        mask = gaussian_filter(mask, sigma=gaussian_sigma).astype(np.float32)
        mask = sanitize_mask(mask)

        # Re-normalize after smoothing.
        central_values_after = central_crop_values(mask, center_crop_fraction)
        central_reference_after = float(np.nanmedian(central_values_after))

        if not np.isfinite(central_reference_after) or central_reference_after <= 0:
            raise ValueError(
                f"Invalid central reference after smoothing for band {band}: "
                f"{central_reference_after}"
            )

        mask = mask / central_reference_after
        mask = sanitize_mask(mask)

    correction_factor = 1.0 / mask

    print(f"  individual center DN min / median / max: "
          f"{np.min(center_values_per_image):.3f} / "
          f"{np.median(center_values_per_image):.3f} / "
          f"{np.max(center_values_per_image):.3f}")

    print(f"  final mask min / median / max: "
          f"{np.nanmin(mask):.4f} / "
          f"{np.nanmedian(mask):.4f} / "
          f"{np.nanmax(mask):.4f}")

    print(f"  correction factor min / median / max: "
          f"{np.nanmin(correction_factor):.4f} / "
          f"{np.nanmedian(correction_factor):.4f} / "
          f"{np.nanmax(correction_factor):.4f}")

    return mask.astype(np.float32), correction_factor.astype(np.float32), reference_profile


def save_float_raster(path, arr, profile):
    """Save float32 single-band raster."""
    out_profile = profile.copy()
    out_profile.update(
        dtype="float32",
        count=1,
        nodata=None
    )

    with rasterio.open(path, "w", **out_profile) as dst:
        dst.write(arr.astype(np.float32), 1)


def save_corrected_raster(path, arr, profile):
    """Save corrected raster either as float32 or uint16."""
    out_profile = profile.copy()
    out_profile.update(count=1, nodata=None)

    if output_dtype.lower() == "float32":
        out_arr = arr.astype(np.float32)
        out_profile.update(dtype="float32")

    elif output_dtype.lower() == "uint16":
        # For uint16 output, invalid values must be replaced before casting.
        arr_safe = np.where(np.isfinite(arr), arr, 0)
        out_arr = np.clip(np.rint(arr_safe), 0, 65535).astype(np.uint16)
        out_profile.update(dtype="uint16")

    else:
        raise ValueError("output_dtype must be either 'float32' or 'uint16'.")

    with rasterio.open(path, "w", **out_profile) as dst:
        dst.write(out_arr, 1)


def apply_mask_to_image(image_path, mask, output_path):
    """
    Apply vignetting mask to one image.

    corrected = image / mask
    """
    arr, profile = read_single_band(image_path)

    if arr.shape != mask.shape:
        raise ValueError(
            f"Image size does not match mask: {image_path.name} has {arr.shape}, "
            f"mask has {mask.shape}."
        )

    mask_safe = sanitize_mask(mask)

    corrected = arr / mask_safe
    corrected = np.where(np.isfinite(corrected), corrected, np.nan)

    save_corrected_raster(output_path, corrected, profile)

    return corrected


# =============================================================================
# MAIN
# =============================================================================

def main():
    flat_dir = Path(flat_field_folder)
    img_dir = Path(image_folder)
    out_dir = Path(output_folder)

    if not flat_dir.exists():
        print(f"Error: flat_field_folder does not exist: {flat_dir}")
        sys.exit(1)

    if not img_dir.exists():
        print(f"Error: image_folder does not exist: {img_dir}")
        sys.exit(1)

    masks_dir = out_dir / "masks"
    corrected_dir = out_dir / "corrected"

    masks_dir.mkdir(parents=True, exist_ok=True)
    corrected_dir.mkdir(parents=True, exist_ok=True)

    flat_images = find_images(flat_dir)
    target_images = find_images(img_dir)

    if not flat_images:
        print("No flat-field images found.")
        sys.exit(1)

    if not target_images:
        print("No target images found.")
        sys.exit(1)

    print(f"Flat-field images found: {len(flat_images)}")
    print(f"Target images found: {len(target_images)}")

    flat_groups = group_by_band(flat_images)
    target_groups = group_by_band(target_images)

    print("\nFlat-field bands:")
    for band, paths in flat_groups.items():
        print(f"  {band}: {len(paths)} image(s)")

    print("\nTarget image bands:")
    for band, paths in target_groups.items():
        print(f"  {band}: {len(paths)} image(s)")

    masks = {}

    # Compute and save masks.
    for band, paths in flat_groups.items():
        try:
            mask, correction_factor, profile = compute_band_mask(paths, band)
        except Exception as e:
            print(f"ERROR computing mask for band {band}: {e}")
            continue

        mask_path = masks_dir / f"vignetting_mask_{band}.tif"
        corr_path = masks_dir / f"correction_factor_{band}.tif"

        save_float_raster(mask_path, mask, profile)
        save_float_raster(corr_path, correction_factor, profile)

        masks[band] = mask

        print(f"  saved mask: {mask_path}")
        print(f"  saved correction factor: {corr_path}")

    if not masks:
        print("No masks were created. Processing stopped.")
        sys.exit(1)

    # Apply masks.
    print("\nApplying masks to target images...")

    corrected_count = 0
    skipped_count = 0

    for band, paths in target_groups.items():
        if band in masks:
            mask = masks[band]
        elif "ALL" in masks:
            mask = masks["ALL"]
            print(f"  band {band}: using ALL mask")
        else:
            print(f"  WARNING: no mask found for band {band}, skipping {len(paths)} image(s).")
            skipped_count += len(paths)
            continue

        for image_path in paths:
            out_name = f"{image_path.stem}_vigncorr.tif"
            out_path = corrected_dir / out_name

            try:
                apply_mask_to_image(image_path, mask, out_path)
                corrected_count += 1
                print(f"  corrected: {image_path.name} -> {out_name}")
            except Exception as e:
                skipped_count += 1
                print(f"  ERROR correcting {image_path.name}: {e}")

    print("\nDone.")
    print(f"Corrected images: {corrected_count}")
    print(f"Skipped images: {skipped_count}")
    print(f"Output folder: {out_dir}")


if __name__ == "__main__":
    main()
