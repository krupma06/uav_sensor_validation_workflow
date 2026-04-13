# =============================================================================
# File:         radiometric_converter.py
# Project:      Master's thesis – Verification of Spectral, Radiometric, and Geometric Properties of DJI Mavic 3M, Matrice 4E, and Matrice 4T Devices
# Author:       Martin KRUPIČKA
# Date:         2025-12-05
# Version:      1.0.0
#
# Description:
#   GUI tool for empirical line method (ELM) radiometric calibration of DJI
#   multispectral bands to reflectance, with optional secondary scene
#   normalisation using in-scene panel ROIs (CSV-based or interactive mouse
#   marking).
#
# Inputs:
#   - Panel close-up folder (GeoTIFFs of calibration panels) + panel CSV (filename,rho)
#   - Images/orthos folder: GeoTIFFs to be calibrated (DJI _MS_ band naming expected)
#   - Optional: scene panels CSV (filename,x0,y0,x1,y1,rho) or interactively
#     marked ROIs via the built-in canvas tool
#
# Outputs:
#   - Calibrated reflectance GeoTIFFs written to output folder with suffix '_refl'
#
# Requirements:
#   - Python >= 3.9
#   - numpy
#   - pandas
#   - rasterio
#   - Pillow
#   - tkinter
#
# Usage:
#   Run: python radiometric_converter.py  (starts the GUI)
#
# Notes:
#   Band is parsed from filename using the DJI '_MS_' token (e.g., DJI_..._MS_G.TIF).
#   Scene normalisation applies a per-image multiplicative correction k derived
#   as the median ratio of target rho to measured rho across all valid ROIs.
#   Negative reflectance values can be clipped to 0 (values > 1 are kept).
#
# =============================================================================

# --------------------------
# Import libraries
# --------------------------
import os           # path handling and directory operations
import traceback    # full stack-trace formatting for error reporting
import numpy as np  # array maths
import rasterio     # GeoTIFF read / write
import pandas as pd # CSV loading and tabular data handling
from PIL import Image, ImageTk  # image scaling and Tk-compatible photo objects

import tkinter as tk                                      # main GUI framework
from tkinter import filedialog, messagebox, scrolledtext  # dialogs and widgets


# --------------------------
# Helper utilities
# --------------------------

def log_msg(msg, logger=None):
    """
    Writes a status message either to the GUI log callback or to standard output

    Args:
        msg (str): The message to be displayed or printed
        logger (callable | None): Optional logging callback used by the GUI
                                  If None, the message is printed to stdout

    Returns:
        None
    """
    # Route a message either to the GUI logger callback or to stdout.
    if logger is not None:
        logger(msg)
    else:
        print(msg)


def get_band_from_filename(fname):
    """
    Extracts the spectral band label from a DJI multispectral filename

    The function expects filenames containing the token '_MS_', for example
    'DJI_0001_MS_G.TIF', from which the band 'G' is returned

    Args:
        fname (str): Input filename or file path

    Returns:
        str | None: Uppercase band label parsed from the filename
                    Returns None when the expected DJI naming convention is not found
    """
    # Parse the spectral band identifier from a DJI multispectral filename.
    # Expected token: '_MS_<BAND>.TIF'  (e.g. DJI_0001_MS_G.TIF -> 'G')
    base = os.path.basename(fname)
    if "_MS_" in base:
        band_part = base.split("_MS_")[1]    # keep everything after '_MS_'
        band = os.path.splitext(band_part)[0]  # strip file extension
        return band.upper()
    return None  # filename does not follow DJI _MS_ convention


def central_crop(arr, frac=0.4):
    """
    Extracts a central rectangular crop from a 2-D raster array

    The crop is defined as a fraction of the original image width and height
    centred around the middle of the array

    Args:
        arr (numpy.ndarray): Input 2-D array representing raster values
        frac (float): Fraction of the image width and height to retain
                      Must be in the interval (0, 1]

    Returns:
        numpy.ndarray: Cropped 2-D array containing the central part of the image
    """
    h, w = arr.shape
    frac = float(frac)
    if not (0 < frac <= 1):
        raise ValueError("frac must be in (0,1].")
    # Compute pixel boundaries symmetrically around the image centre
    x0 = int((1 - frac) / 2 * w)
    x1 = int((1 + frac) / 2 * w)
    y0 = int((1 - frac) / 2 * h)
    y1 = int((1 + frac) / 2 * h)
    # Guard against degenerate crops caused by very small arrays
    if x1 <= x0:
        x1 = x0 + 1
    if y1 <= y0:
        y1 = y0 + 1
    return arr[y0:y1, x0:x1]


# --------------------------
# Panel DN extraction
# --------------------------

def compute_panel_dn_center(panel_dir, csv_path, center_frac=0.4, logger=None):
    """
    Computes mean DN values from the central crop of close-up panel images

    The function reads a CSV table containing panel filenames and target reflectance
    values, opens the corresponding rasters, extracts a central crop, and stores the
    mean DN together with the known reflectance for each spectral band

    Args:
        panel_dir (str): Directory containing close-up panel GeoTIFF files
        csv_path (str): Path to the CSV file with columns 'filename' and 'rho'
        center_frac (float): Fraction of the image used for the central crop
        logger (callable | None): Optional logging callback for progress messages

    Returns:
        dict: Dictionary keyed by band label with lists of measured DN and target rho
              values in the form {'BAND': {'dn': [...], 'rho': [...]}}
    """
    log_msg("Loading panel CSV (closeup) ...", logger)
    table = pd.read_csv(csv_path)
    if "filename" not in table.columns or "rho" not in table.columns:
        raise ValueError("CSV must have 'filename' and 'rho'.")

    panel_stats = {}
    for _, row in table.iterrows():
        fname = row["filename"]
        rho   = float(row["rho"])
        path  = os.path.join(panel_dir, fname)

        if not os.path.isfile(path):
            log_msg(f"Panel file '{path}' not found, skipping.", logger)
            continue

        # Extract band label from the filename
        band = get_band_from_filename(fname)
        if band is None:
            log_msg(f"Cannot parse band from '{fname}', skipping.", logger)
            continue

        with rasterio.open(path) as src:
            arr  = src.read(1).astype("float32")
            crop = central_crop(arr, center_frac)

            # Build a validity mask: exclude nodata or non-finite pixels
            if src.nodata is not None:
                valid = crop != src.nodata
            else:
                valid = np.isfinite(crop)

            if np.count_nonzero(valid) == 0:
                log_msg(f"No valid pixels in panel '{fname}', skipping.", logger)
                continue

            dn_mean = float(crop[valid].mean())

        # Accumulate DN and target rho per band for subsequent ELM fitting
        panel_stats.setdefault(band, {"dn": [], "rho": []})
        panel_stats[band]["dn"].append(dn_mean)
        panel_stats[band]["rho"].append(rho)

    return panel_stats


# --------------------------
# ELM coefficient fitting
# --------------------------

def fit_elm(panel_stats, logger=None):
    """
    Fits empirical line method calibration coefficients for each spectral band

    For every band, a linear model of the form rho = a * DN + b is estimated from
    the panel measurements. If only one calibration panel is available, the intercept
    is forced to zero and only the gain term is estimated

    Args:
        panel_stats (dict): Dictionary of panel DN and reflectance values grouped by band
        logger (callable | None): Optional logging callback for reporting coefficients

    Returns:
        dict: Dictionary keyed by band containing fitted coefficients and metadata
              in the form {'BAND': {'a': ..., 'b': ..., 'r2': ..., 'n': ...}}
    """
    # Fit a linear model  rho = a * DN + b  for each band using the collected panel measurements.  With a single panel point, only the gain (a) is estimated (b = 0).
    coeffs = {}
    for band, stats in panel_stats.items():
        dn_arr  = np.array(stats["dn"],  dtype="float64")
        rho_arr = np.array(stats["rho"], dtype="float64")
        n = len(dn_arr)

        if n == 0:
            continue

        if n == 1:
            # Single-point calibration: force intercept to zero
            a  = rho_arr[0] / dn_arr[0] if dn_arr[0] != 0 else 0.0
            b  = 0.0
            r2 = np.nan
        else:
            # Ordinary least-squares linear regression
            a, b = np.polyfit(dn_arr, rho_arr, 1)
            pred   = a * dn_arr + b
            ss_res = np.sum((rho_arr - pred) ** 2)
            ss_tot = np.sum((rho_arr - np.mean(rho_arr)) ** 2)
            r2     = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan

        coeffs[band] = {"a": a, "b": b, "r2": r2, "n": n}
        
        # Log the calibration coefficients for this band
        if np.isnan(r2):
            log_msg(f"Band {band}: a={a:.6f}, b={b:.6f}, n={n} (single panel)", logger)
        else:
            log_msg(f"Band {band}: a={a:.6f}, b={b:.6f}, R²={r2:.4f}, n={n}", logger)

    return coeffs


# --------------------------
# Panel crop preview
# --------------------------

def create_panel_crop_preview(panel_dir, csv_path, center_frac, logger=None):
    """
    Creates a contrast-stretched preview of the central crop of a panel image

    The function loads the first valid panel raster listed in the CSV, extracts its
    central crop, applies a 2–98 % percentile stretch, saves the result as a PNG file,
    and opens the preview for visual inspection

    Args:
        panel_dir (str): Directory containing close-up panel GeoTIFF files
        csv_path (str): Path to the CSV file listing panel filenames
        center_frac (float): Fraction of image width and height used for the crop
        logger (callable | None): Optional logging callback

    Returns:
        str: Path to the saved PNG preview file
    """
    table = pd.read_csv(csv_path)
    if "filename" not in table.columns:
        raise ValueError("CSV must have 'filename'.")

    for _, row in table.iterrows():
        fname = row["filename"]
        path  = os.path.join(panel_dir, fname)
        if not os.path.isfile(path):
            continue

        with rasterio.open(path) as src:
            arr   = src.read(1).astype("float32")
            crop  = central_crop(arr, center_frac)
            valid = np.isfinite(crop)

            if np.count_nonzero(valid) == 0:
                raise RuntimeError("No valid pixels in crop.")

            # Percentile stretch for better visual contrast
            vmin = np.percentile(crop[valid], 2)
            vmax = np.percentile(crop[valid], 98)
            if vmax <= vmin:  # fall back to full range if stretch collapses
                vmin = float(crop[valid].min())
                vmax = float(crop[valid].max())

            if vmax > vmin:
                scaled = (crop - vmin) / (vmax - vmin)
            else:
                scaled = np.zeros_like(crop)

            # Convert to 8-bit grayscale for PNG export
            scaled = np.clip(scaled, 0, 1) * 255.0
            img    = Image.fromarray(scaled.astype("uint8"), mode="L")
            name, _ = os.path.splitext(fname)
            preview_path = os.path.join(panel_dir, f"{name}_crop_preview.png")
            img.save(preview_path)
            img.show()
            return preview_path  # return after the first successfully processed file

    raise FileNotFoundError("No existing panel file in CSV.")


# --------------------------
# Scene normalisation
# --------------------------

def apply_scene_normalisation(rho, rois, fname, logger=None):
    """
    Applies secondary multiplicative normalisation using in-scene panel ROIs

    For each valid ROI, a correction factor is computed as the ratio between the target
    reflectance and the measured reflectance within the ROI. The final image-wide
    correction is defined as the median of all valid ROI correction factors

    Args:
        rho (numpy.ndarray): Calibrated reflectance raster to be normalised
        rois (list[dict]): List of ROI records with keys x0, y0, x1, y1, and rho
        fname (str): Filename of the processed raster, used for context or logging
        logger (callable | None): Optional logging callback

    Returns:
        tuple: Three-element tuple containing:
            - numpy.ndarray: Normalised reflectance raster
            - float: Final multiplicative correction factor k
            - int: Number of valid ROIs used in the correction
    """
    h, w = rho.shape
    ks = []

    for roi in rois:
        # Clamp ROI coordinates to image bounds
        x0    = max(0, min(int(roi["x0"]), w - 1))
        x1    = max(0, min(int(roi["x1"]), w - 1))
        y0    = max(0, min(int(roi["y0"]), h - 1))
        y1    = max(0, min(int(roi["y1"]), h - 1))
        rho_t = float(roi["rho"])

        if x1 < x0 or y1 < y0:  # degenerate ROI – skip
            continue

        crop  = rho[y0:y1+1, x0:x1+1]
        valid = np.isfinite(crop)
        if np.count_nonzero(valid) == 0:
            continue

        mean_panel = float(crop[valid].mean())
        if mean_panel <= 0:  # avoid division by zero or negative reflectance
            continue

        k_i = rho_t / mean_panel  # per-ROI correction factor
        ks.append(k_i)

    if not ks:  # no valid ROIs found – return image unchanged
        return rho, 1.0, 0

    # Use median to suppress outlier panels
    k = float(np.median(ks))
    return rho * k, k, len(ks)


# --------------------------
# Single-image calibration
# --------------------------

def apply_calibration_to_image(
    in_path,
    out_path,
    coeffs,
    clip_negative=True,
    logger=None,
    scene_rois_for_file=None,
):
    """
    Applies radiometric calibration and optional scene normalisation to one image

    The function reads a GeoTIFF, identifies its spectral band from the filename,
    applies the corresponding empirical line model, optionally performs secondary
    scene normalisation using predefined ROIs, and writes the result as a float32 raster

    Args:
        in_path (str): Path to the input GeoTIFF file
        out_path (str): Path where the calibrated GeoTIFF will be written
        coeffs (dict): Dictionary of ELM coefficients keyed by spectral band
        clip_negative (bool): Whether negative reflectance values should be clipped to 0
        logger (callable | None): Optional logging callback
        scene_rois_for_file (list[dict] | None): Optional list of in-scene panel ROIs for
                                                secondary normalisation of the current file

    Returns:
        None
    """
    base       = os.path.basename(in_path)
    band_label = get_band_from_filename(base)  # derive band from filename

    with rasterio.open(in_path) as src:
        profile = src.profile
        profile.update(dtype="float32")  # output always stored as float32
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        coeff_for_band = coeffs.get(band_label, None)  # None if band is unknown

        with rasterio.open(out_path, "w", **profile) as dst:
            for i in range(1, src.count + 1):
                data = src.read(i).astype("float32")

                # Apply linear ELM model:  rho = a * DN + b
                if coeff_for_band is not None:
                    a   = coeff_for_band["a"]
                    b   = coeff_for_band["b"]
                    rho = a * data + b
                else:
                    rho = data  # no calibration available for this band

                # Optional secondary scene normalisation
                if scene_rois_for_file:
                    rho, k, n_used = apply_scene_normalisation(
                        rho, scene_rois_for_file, base, logger=logger
                    )

                # Clip unphysical negative reflectance values
                if clip_negative:
                    rho[rho < 0] = 0.0

                dst.write(rho.astype("float32"), i)


# --------------------------
# Batch folder calibration
# --------------------------

def apply_calibration_to_folder(
    images_dir,
    out_dir,
    coeffs,
    clip_negative=True,
    suffix="_refl",
    logger=None,
    scene_rois=None,
):
    """
    Applies radiometric calibration to all GeoTIFF files in a folder

    The function iterates through the input directory, calibrates every TIFF image
    using previously fitted ELM coefficients, optionally applies scene normalisation,
    and saves the outputs to the selected output directory

    Args:
        images_dir (str): Directory containing input GeoTIFF images
        out_dir (str): Directory where calibrated outputs will be saved
        coeffs (dict): Dictionary of ELM coefficients keyed by spectral band
        clip_negative (bool): Whether negative reflectance values should be clipped to 0
        suffix (str): Suffix appended to output filenames before the extension
        logger (callable | None): Optional logging callback
        scene_rois (dict | None): Optional dictionary mapping filenames to scene ROIs

    Returns:
        None
    """
    # Iterate over all GeoTIFFs in images_dir and calibrate each one.
    if not coeffs:
        log_msg("No coeffs.", logger)
        return

    files = [f for f in os.listdir(images_dir) if f.lower().endswith((".tif", ".tiff"))]
    if not files:
        log_msg("No tif files.", logger)
        return

    os.makedirs(out_dir, exist_ok=True)

    for i, fname in enumerate(files, 1):
        in_path   = os.path.join(images_dir, fname)
        name, ext = os.path.splitext(fname)
        out_path  = os.path.join(out_dir, f"{name}{suffix}{ext}")  # append '_refl' suffix

        # Look up per-file scene ROIs (None if scene normalisation is disabled)
        rois_for_file = None
        if scene_rois is not None:
            rois_for_file = scene_rois.get(fname)

        apply_calibration_to_image(
            in_path=in_path,
            out_path=out_path,
            coeffs=coeffs,
            clip_negative=clip_negative,
            logger=logger,
            scene_rois_for_file=rois_for_file,
        )


# =============================================================================
# GUI class
# =============================================================================

class CalibrationGUI:
    """
    Graphical user interface for ELM-based radiometric calibration

    The class provides widgets for selecting input folders and CSV files, previewing
    panel crops, marking scene ROIs interactively, and running the full calibration
    workflow from close-up panels to calibrated reflectance rasters
    """

    # --------------------------
    # Initialisation
    # --------------------------

    def __init__(self, root):
        """
        Initialises the calibration GUI and its state variables

        Args:
            root (tk.Tk): Root Tkinter window used as the main application window

        Returns:
            None
        """
        self.root = root
        self.root.title("ELM multispectral calibration tool")

        # Tkinter variables bound to GUI widgets
        self.panel_dir_var         = tk.StringVar()
        self.panel_csv_var         = tk.StringVar()
        self.images_dir_var        = tk.StringVar()
        self.out_dir_var           = tk.StringVar()
        self.clip_negative_var     = tk.IntVar(value=1)     # clip <0 to 0 by default
        self.center_frac_var       = tk.DoubleVar(value=0.4)  # 40 % central crop
        self.enable_scene_norm_var = tk.IntVar(value=0)     # scene normalisation off by default
        self.scene_csv_var         = tk.StringVar()
        self.scene_rois_manual     = {}  # filename -> list of manually marked ROIs

        self.build_layout()

    # --------------------------
    # Layout construction
    # --------------------------

    def build_layout(self):
        """
        Builds and places all widgets forming the main GUI layout

        The layout includes path selectors, option toggles, action buttons, and
        a scrollable logging panel used to report processing progress and errors

        Returns:
            None
        """
        pad = {"padx": 5, "pady": 3}
        row = 0

        # Row 0 – panel close-up folder
        tk.Label(self.root, text="Panel closeup folder:").grid(row=row, column=0, sticky="w", **pad)
        tk.Entry(self.root, textvariable=self.panel_dir_var, width=50).grid(row=row, column=1, **pad)
        tk.Button(self.root, text="Browse", command=self.browse_panel_dir).grid(row=row, column=2, **pad)
        row += 1

        # Row 1 – panel CSV
        tk.Label(self.root, text="Panel CSV (filename,rho):").grid(row=row, column=0, sticky="w", **pad)
        tk.Entry(self.root, textvariable=self.panel_csv_var, width=50).grid(row=row, column=1, **pad)
        tk.Button(self.root, text="Browse", command=self.browse_panel_csv).grid(row=row, column=2, **pad)
        row += 1

        # Row 2 – images / orthos folder
        tk.Label(self.root, text="Images/orthos folder:").grid(row=row, column=0, sticky="w", **pad)
        tk.Entry(self.root, textvariable=self.images_dir_var, width=50).grid(row=row, column=1, **pad)
        tk.Button(self.root, text="Browse", command=self.browse_images_dir).grid(row=row, column=2, **pad)
        row += 1

        # Row 3 – output folder
        tk.Label(self.root, text="Output folder:").grid(row=row, column=0, sticky="w", **pad)
        tk.Entry(self.root, textvariable=self.out_dir_var, width=50).grid(row=row, column=1, **pad)
        tk.Button(self.root, text="Browse", command=self.browse_out_dir).grid(row=row, column=2, **pad)
        row += 1

        # Row 4 – central crop fraction + preview button
        tk.Label(self.root, text="Closeup crop of panels (0–1):").grid(row=row, column=0, sticky="w", **pad)
        tk.Entry(self.root, textvariable=self.center_frac_var, width=10).grid(row=row, column=1, sticky="w", **pad)
        tk.Button(self.root, text="Preview closeup crop", command=self.preview_crop).grid(row=row, column=2, **pad)
        row += 1

        # Row 5 – toggle secondary normalisation
        tk.Checkbutton(
            self.root,
            text="Enable secondary normalisation",
            variable=self.enable_scene_norm_var,
        ).grid(row=row, column=0, columnspan=3, sticky="w", **pad)
        row += 1

        # Row 6 – optional scene panels CSV
        tk.Label(self.root, text="Scene panels CSV (filename,x0,y0,x1,y1,rho):").grid(row=row, column=0, sticky="w", **pad)
        tk.Entry(self.root, textvariable=self.scene_csv_var, width=50).grid(row=row, column=1, **pad)
        tk.Button(self.root, text="Browse", command=self.browse_scene_csv).grid(row=row, column=2, **pad)
        row += 1

        # Row 7 – launch interactive ROI marking tool
        tk.Button(
            self.root,
            text="Select panels in scene manually",
            command=self.interactive_mark_scene_panels,
        ).grid(row=row, column=0, columnspan=3, sticky="w", **pad)
        row += 1

        # Row 8 – clip negative reflectance toggle
        tk.Checkbutton(
            self.root,
            text="Clip values <0 to 0",
            variable=self.clip_negative_var,
        ).grid(row=row, column=0, columnspan=3, sticky="w", **pad)
        row += 1

        # Row 9 – run calibration button (green highlight)
        tk.Button(
            self.root,
            text="Run calibration",
            command=self.start_calibration,
            bg="#4caf50",
            fg="white",
        ).grid(row=row, column=0, columnspan=3, pady=(10, 5))
        row += 1

        # Row 10/11 – scrollable log output
        tk.Label(self.root, text="Log:").grid(row=row, column=0, sticky="w", **pad)
        row += 1
        self.log_text = scrolledtext.ScrolledText(self.root, width=90, height=22, state="disabled")
        self.log_text.grid(row=row, column=0, columnspan=3, padx=5, pady=5)

    # --------------------------
    # Logging
    # --------------------------

    def gui_log(self, msg):
        """
        Appends a message to the GUI log window

        Args:
            msg (str): Message text to be inserted into the scrollable log widget

        Returns:
            None
        """
        # Append a message to the scrollable log widget and scroll to the bottom.
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.root.update_idletasks()  # force immediate redraw

    # --------------------------
    # Browse callbacks
    # --------------------------

    def browse_panel_dir(self):
        """
        Opens a dialog for selecting the close-up panel image folder

        Returns:
            None
        """
        d = filedialog.askdirectory(title="Panel closeup folder")
        if d:
            self.panel_dir_var.set(d)

    def browse_panel_csv(self):
        """
        Opens a dialog for selecting the panel CSV file

        Returns:
            None
        """
        f = filedialog.askopenfilename(
            title="Panel CSV",
            filetypes=[("CSV", "*.csv"), ("All", "*.*")]
        )
        if f:
            self.panel_csv_var.set(f)

    def browse_images_dir(self):
        """
        Opens a dialog for selecting the input image or ortho folder

        Returns:
            None
        """
        d = filedialog.askdirectory(title="Images/orthos folder")
        if d:
            self.images_dir_var.set(d)

    def browse_out_dir(self):
        """
        Opens a dialog for selecting the output folder

        Returns:
            None
        """
        d = filedialog.askdirectory(title="Output folder")
        if d:
            self.out_dir_var.set(d)

    def browse_scene_csv(self):
        """
        Opens a dialog for selecting the scene panel ROI CSV file

        Returns:
            None
        """
        f = filedialog.askopenfilename(
            title="Scene panels CSV",
            filetypes=[("CSV", "*.csv"), ("All", "*.*")]
        )
        if f:
            self.scene_csv_var.set(f)

    # --------------------------
    # Panel crop preview
    # --------------------------

    def preview_crop(self):
        """
        Validates preview inputs and generates a panel crop preview

        Returns:
            None
        """
        # Validate inputs and call the preview helper, reporting errors to log.
        panel_dir = self.panel_dir_var.get().strip()
        panel_csv = self.panel_csv_var.get().strip()

        if not panel_dir or not os.path.isdir(panel_dir):
            messagebox.showerror("Error", "Invalid panel closeup folder.")
            return
        if not panel_csv or not os.path.isfile(panel_csv):
            messagebox.showerror("Error", "Invalid panel CSV.")
            return
        try:
            center_frac = float(self.center_frac_var.get())
        except ValueError:
            messagebox.showerror("Error", "Center fraction must be numeric (e.g. 0.4).")
            return
        if not (0 < center_frac <= 1):
            messagebox.showerror("Error", "Center fraction must be in (0,1].")
            return
        try:
            create_panel_crop_preview(panel_dir, panel_csv, center_frac, logger=self.gui_log)
        except Exception as e:
            tb = traceback.format_exc()
            self.gui_log("Error in preview:\n" + tb)
            messagebox.showerror("Error", str(e))

    # --------------------------
    # Interactive scene ROI marking
    # --------------------------

    def interactive_mark_scene_panels(self):
        """
        Launches an interactive tool for manual marking of in-scene panel ROIs

        The tool opens each raster in sequence, allows zooming and panning, and lets
        the user define rectangular ROIs by clicking two corner points and assigning
        a target reflectance value

        Returns:
            None
        """
        # Open a zoomable / pannable canvas window for each image in the folder,
        # letting the user click two corner points to define a panel ROI.
        images_dir = self.images_dir_var.get().strip()
        if not images_dir or not os.path.isdir(images_dir):
            messagebox.showerror("Error", "Set valid images/orthos folder first.")
            return

        files = [f for f in sorted(os.listdir(images_dir)) if f.lower().endswith((".tif", ".tiff"))]
        if not files:
            messagebox.showerror("Error", "No TIF/TIFF files in images folder.")
            return

        self.scene_rois_manual = {}  # reset previously collected manual ROIs
        self.gui_log("=== Interactive scene panel marking (zoom + pan) ===")
        self.gui_log(f"Files: {len(files)}")

        def label_one(idx):
            # Recursively show one image at a time; terminates when all are processed.
            if idx >= len(files):
                messagebox.showinfo(
                    "Done",
                    "Interactive marking finished.\n"
                    "Saved ROIs will be used for secondary normalisation."
                )
                self.gui_log("Interactive marking finished.")
                return

            fname = files[idx]
            path  = os.path.join(images_dir, fname)

            # Load raster band 1 for display
            with rasterio.open(path) as src:
                arr = src.read(1).astype("float32")

            valid = np.isfinite(arr)
            if np.count_nonzero(valid) == 0:
                self.gui_log(f"{fname}: no valid pixels, skipping interactive marking.")
                return label_one(idx + 1)

            # Percentile stretch (2–98 %) for display contrast
            vmin = np.percentile(arr[valid], 2)
            vmax = np.percentile(arr[valid], 98)
            if vmax <= vmin:
                vmin = float(arr[valid].min())
                vmax = float(arr[valid].max())

            if vmax > vmin:
                scaled = (arr - vmin) / (vmax - vmin)
            else:
                scaled = np.zeros_like(arr)

            # Convert to 8-bit grayscale for display
            scaled    = np.clip(scaled, 0, 1) * 255.0
            img_uint8 = scaled.astype("uint8")
            h, w      = img_uint8.shape
            base_img  = Image.fromarray(img_uint8, mode="L")

            top = tk.Toplevel(self.root)
            top.title(f"Mark panel (zoom + pan): {fname}")

            # Initial scale so the image fits inside max_size × max_size pixels
            max_size   = 800
            init_scale = min(max_size / w, max_size / h)
            if init_scale <= 0:
                init_scale = 1.0
            scale = [init_scale]  # stored in a list so nested functions can mutate it

            # Canvas viewport – the image can exceed this size (scrollregion expands)
            VIEW_SIZE = 800
            canvas = tk.Canvas(top, width=VIEW_SIZE, height=VIEW_SIZE, bg="black")
            canvas.grid(row=0, column=0, rowspan=6)

            # Instruction label
            info = tk.Label(
                top,
                text=(
                    "LEFT button: 1st corner → 2nd corner of panel ROI\n"
                    "Mouse wheel: zoom in / out\n"
                    "RIGHT button: drag to pan\n"
                    "Enter target rho and click 'Save and next'."
                ),
                justify="left",
            )
            info.grid(row=0, column=1, sticky="nw", padx=5, pady=5)

            rho_var = tk.DoubleVar(value=0.95)  # default target reflectance
            tk.Label(top, text="Target panel rho:").grid(row=1, column=1, sticky="w", padx=5, pady=2)
            tk.Entry(top, textvariable=rho_var, width=10).grid(row=2, column=1, sticky="w", padx=5, pady=2)

            roi       = {"x0": None, "y0": None, "x1": None, "y1": None}  # current ROI corners
            photo_ref = {"img": None}  # holds PhotoImage reference to prevent garbage collection

            def redraw():
                # Resize the base image to the current zoom level and refresh the canvas.
                s      = scale[0]
                disp_w = int(w * s)
                disp_h = int(h * s)

                img_resized = base_img.resize((disp_w, disp_h), Image.BILINEAR)
                photo       = ImageTk.PhotoImage(img_resized)
                photo_ref["img"] = photo  # keep reference alive

                canvas.delete("all")
                canvas.create_image(0, 0, image=photo, anchor="nw")
                canvas.config(scrollregion=(0, 0, disp_w, disp_h))

                # Draw the current ROI rectangle if both corners have been set
                if roi["x0"] is not None and roi["x1"] is not None:
                    x0 = min(roi["x0"], roi["x1"]) * s
                    x1 = max(roi["x0"], roi["x1"]) * s
                    y0 = min(roi["y0"], roi["y1"]) * s
                    y1 = max(roi["y0"], roi["y1"]) * s
                    canvas.create_rectangle(
                        x0, y0, x1, y1,
                        outline="red",
                        width=2,
                        tags="roi_rect",
                    )

            def on_click(event):
                # Left-click: record ROI corners in original image pixel coordinates
                # (accounts for the current zoom level and canvas scroll offset).
                s  = scale[0]
                cx = canvas.canvasx(event.x)  # canvas-world X (includes scroll offset)
                cy = canvas.canvasy(event.y)  # canvas-world Y
                x  = int(cx / s)
                y  = int(cy / s)
                x  = max(0, min(w - 1, x))
                y  = max(0, min(h - 1, y))

                if roi["x0"] is None:
                    roi["x0"], roi["y0"] = x, y  # first corner
                else:
                    roi["x1"], roi["y1"] = x, y  # second corner
                redraw()

            def on_wheel(event):
                # Mouse-wheel zoom: multiply / divide scale by a fixed step.
                zoom_factor = 1.2

                if event.delta > 0:
                    scale[0] *= zoom_factor
                else:
                    scale[0] /= zoom_factor

                # Clamp zoom: at least 25 % of initial scale, at most 30× initial scale
                scale[0] = max(init_scale * 0.25, min(init_scale * 30.0, scale[0]))
                redraw()

            # Pan with right mouse button
            def on_pan_start(event):
                canvas.scan_mark(event.x, event.y)

            def on_pan_move(event):
                canvas.scan_dragto(event.x, event.y, gain=1)

            # Bind mouse events to the canvas
            canvas.bind("<Button-1>",   on_click)
            canvas.bind("<MouseWheel>", on_wheel)
            canvas.bind("<Button-3>",   on_pan_start)
            canvas.bind("<B3-Motion>",  on_pan_move)

            redraw()

            def save_and_next():
                # Validate the ROI and target rho, store the result, move to next image.
                if roi["x0"] is None or roi["y0"] is None or roi["x1"] is None or roi["y1"] is None:
                    messagebox.showerror("Error", "Click two panel corners first.")
                    return
                try:
                    rho_target = float(rho_var.get())
                except ValueError:
                    messagebox.showerror("Error", "Target rho must be a number.")
                    return

                # Normalise corner order (top-left / bottom-right)
                x0 = min(roi["x0"], roi["x1"])
                x1 = max(roi["x0"], roi["x1"])
                y0 = min(roi["y0"], roi["y1"])
                y1 = max(roi["y0"], roi["y1"])

                rec = {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "rho": rho_target}
                self.scene_rois_manual.setdefault(fname, []).append(rec)
                self.gui_log(
                    f"{fname}: saved ROI ({x0},{y0})–({x1},{y1}), target rho={rho_target}"
                )
                top.destroy()
                label_one(idx + 1)  # advance to the next image

            def skip_and_next():
                # Skip the current image without saving an ROI.
                self.gui_log(f"{fname}: skipped (no ROI).")
                top.destroy()
                label_one(idx + 1)

            # Action buttons
            tk.Button(top, text="Save and next",  command=save_and_next).grid(row=3, column=1, sticky="w", padx=5, pady=5)
            tk.Button(top, text="Skip image",     command=skip_and_next).grid(row=4, column=1, sticky="w", padx=5, pady=5)
            tk.Button(top, text="Cancel marking", command=lambda: top.destroy()).grid(row=5, column=1, sticky="w", padx=5, pady=5)

            top.grab_set()  # block interaction with the main window while marking

        label_one(0)  # start with the first image

    # --------------------------
    # Calibration entry point
    # --------------------------

    def start_calibration(self):
        """
        Validates GUI inputs and runs the full calibration workflow

        The workflow includes extraction of panel DN values, fitting of empirical line
        coefficients, optional loading or merging of scene ROIs, and batch export of
        calibrated reflectance rasters

        Returns:
            None
        """
        # Read and validate all GUI inputs, then execute the full ELM calibration
        # pipeline: panel fitting -> optional scene normalisation -> batch export.

        # Collect GUI values
        panel_dir         = self.panel_dir_var.get().strip()
        panel_csv         = self.panel_csv_var.get().strip()
        images_dir        = self.images_dir_var.get().strip()
        out_dir           = self.out_dir_var.get().strip()
        clip_negative     = bool(self.clip_negative_var.get())
        enable_scene_norm = bool(self.enable_scene_norm_var.get())
        scene_csv         = self.scene_csv_var.get().strip()

        # Validate center fraction
        try:
            center_frac = float(self.center_frac_var.get())
        except ValueError:
            messagebox.showerror("Error", "Center fraction must be numeric (e.g. 0.4).")
            return
        if not (0 < center_frac <= 1):
            messagebox.showerror("Error", "Center fraction must be in (0,1].")
            return

        # Validate required paths
        if not panel_dir or not os.path.isdir(panel_dir):
            messagebox.showerror("Error", "Invalid panel closeup folder.")
            return
        if not panel_csv or not os.path.isfile(panel_csv):
            messagebox.showerror("Error", "Invalid panel CSV.")
            return
        if not images_dir or not os.path.isdir(images_dir):
            messagebox.showerror("Error", "Invalid images/orthos folder.")
            return
        if not out_dir:
            messagebox.showerror("Error", "Invalid output folder.")
            return

        # Build scene ROI dictionary from CSV and/or interactive marking
        scene_rois = {}
        if enable_scene_norm:
            # Load ROIs from CSV if provided
            if scene_csv and os.path.isfile(scene_csv):
                df = pd.read_csv(scene_csv)
                required = {"filename", "x0", "y0", "x1", "y1", "rho"}
                if required.issubset(df.columns):
                    for _, row in df.iterrows():
                        fname = str(row["filename"])
                        try:
                            x0    = int(row["x0"])
                            y0    = int(row["y0"])
                            x1    = int(row["x1"])
                            y1    = int(row["y1"])
                            rho_t = float(row["rho"])
                        except Exception:
                            continue
                        rec = {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "rho": rho_t}
                        scene_rois.setdefault(fname, []).append(rec)
                else:
                    messagebox.showerror(
                        "Error",
                        "Scene CSV must have columns: filename,x0,y0,x1,y1,rho.",
                    )
                    return

            # Merge manually marked ROIs (may overlap with CSV entries)
            if self.scene_rois_manual:
                for fname, rois in self.scene_rois_manual.items():
                    scene_rois.setdefault(fname, []).extend(rois)

            if not scene_rois:
                messagebox.showerror(
                    "Error",
                    "Secondary normalisation is enabled, but no scene ROIs are defined "
                    "(neither CSV nor interactive).",
                )
                return

        # Clear the log widget before a new run
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        # Print run summary to the log
        self.gui_log("=== ELM calibration (closeup panels + optional scene ROIs) ===")
        self.gui_log(f"Panels (closeup):  {panel_dir}")
        self.gui_log(f"Panel CSV:         {panel_csv}")
        self.gui_log(f"Images/orthos:     {images_dir}")
        self.gui_log(f"Output:            {out_dir}")
        self.gui_log(f"Center frac:       {center_frac:.2f}")
        self.gui_log(f"Clip <0:           {'YES' if clip_negative else 'NO'}")
        self.gui_log(f"Scene norm:        {'YES' if enable_scene_norm else 'NO'}")

        # Execute calibration pipeline
        try:
            # Step 1 – extract mean DN from panel close-ups
            panel_stats = compute_panel_dn_center(
                panel_dir=panel_dir,
                csv_path=panel_csv,
                center_frac=center_frac,
                logger=self.gui_log,
            )
            if not panel_stats:
                self.gui_log("No panel stats, abort.")
                return

            # Step 2 – fit ELM linear model per band
            coeffs = fit_elm(panel_stats, logger=self.gui_log)
            if not coeffs:
                self.gui_log("No ELM coeffs, abort.")
                return

            # Step 3 – apply calibration to all images in the folder
            apply_calibration_to_folder(
                images_dir=images_dir,
                out_dir=out_dir,
                coeffs=coeffs,
                clip_negative=clip_negative,
                suffix="_refl",
                logger=self.gui_log,
                scene_rois=scene_rois if enable_scene_norm else None,
            )
            self.gui_log("Done.")
            messagebox.showinfo("Done", "Calibration finished.")

        except Exception as e:
            tb = traceback.format_exc()
            self.gui_log("Error during calibration:\n" + tb)
            messagebox.showerror("Error", str(e))


# --------------------------
# Entry point
# --------------------------

if __name__ == "__main__":
    root = tk.Tk()
    app  = CalibrationGUI(root)
    root.mainloop()
