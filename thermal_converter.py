# =============================================================================
# File:         thermal_converter.py
# Project:      Master's thesis – Verification of Spectral, Radiometric, and Geometric Properties of DJI Mavic 3M, Matrice 4E, and Matrice 4T Devices
# Author:       Martin KRUPIČKA
# Date:         2025-10-04
# Version:      1.0.0
#
# Description:
#   GUI batch converter for DJI thermal R-JPEG files to single-band
#   temperature TIFFs (°C) using DJI Thermal SDK (dji_irp.exe) with manual
#   environmental parameters.
#
# Inputs:
#   - Input folder containing DJI thermal JPG/JPEG (R-JPEG)
#   - Path to DJI Thermal SDK executable dji_irp.exe
#   - Manual parameters: emissivity, distance, humidity, ambient temperature, reflected temperature
#
# Outputs:
#   - Float32 TIFF temperature rasters (°C), one output TIFF per input JPEG
#
# Requirements:
#   - Python >= 3.9
#   - numpy
#   - tifffile
#   - tkinter
#   - DJI Thermal SDK v1.8 (dji_irp.exe)
#
# Usage:
#   Run: python thermal_converter.py  (starts the GUI)
#
# Notes:
#   The script detects RAW output dtype/shape by file size and converts int16 to °C by dividing by 10 when needed.
#   Temporary .raw files can be deleted after successful conversion.
#
# =============================================================================
import os
import subprocess
import tempfile
import traceback
from threading import Thread

import numpy as np
import tifffile

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk


DEFAULT_DJI_IRP = r"Put/Your/DJI/Thermal/SDK/dji_irp.exe" # <-- CHANGE THIS to your dji_irp.exe path now or in the GUI

# Most common DJI thermal shapes
PRIORITY_SHAPES = [
    (640, 512),
    (640, 480),
    (336, 256),
    (328, 256),
    (320, 240),
]


# ============================================================
# DJI IRP CALL (V1.8)
# ============================================================

def call_dji_irp_measure(exe_path, input_jpg, out_raw, params):
    """
    action=measure -> outputs RAW temperature image (dtype may be int16 or float32)
    V1.8 flags: --ambient, --reflection
    measurefmt:
      0 = int16
      1 = float32
    We'll request float32, but still detect real output by RAW size.
    """
    cmd = [
        exe_path,
        "-s", input_jpg,
        "-a", "measure",
        "-o", out_raw,
        "--measurefmt", "1",  # request float32

        "--emissivity", str(params["emissivity"]),
        "--distance",   str(params["distance"]),
        "--humidity",   str(params["humidity"]),
        "--ambient",    str(params["ambient"]),
        "--reflection", str(params["reflected"]),
    ]

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    outtxt = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, outtxt, cmd


# ============================================================
# RAW READING (dtype + shape by file size)
# ============================================================

def _try_read(raw_path, dtype, shape):
    """
    Attempts to read a RAW raster using the supplied dtype and image shape.

    Args:
        raw_path (str): Path to the temporary RAW file produced by DJI Thermal SDK.
        dtype (numpy.dtype): Expected numpy data type of the RAW file.
        shape (tuple[int, int]): Expected image shape as (width, height).

    Returns:
        numpy.ndarray | None: A 2-D array reshaped to (height, width) when the
            file size matches the expected dimensions, otherwise None.
    """
    w, h = shape
    data = np.fromfile(raw_path, dtype=dtype)
    if data.size != w * h:
        return None
    return data.reshape((h, w))


def read_raw_smart(raw_path):
    """
    Detect RAW dtype + shape by file size.
    Returns: arr, dtype_name, (w,h)
    """
    size_bytes = os.path.getsize(raw_path)

    # Prefer INT16 on known shapes
    for (w, h) in PRIORITY_SHAPES:
        if size_bytes == w * h * 2:
            arr = _try_read(raw_path, np.int16, (w, h))
            if arr is not None:
                return arr, "int16", (w, h)

    # Then FLOAT32 on known shapes
    for (w, h) in PRIORITY_SHAPES:
        if size_bytes == w * h * 4:
            arr = _try_read(raw_path, np.float32, (w, h))
            if arr is not None:
                return arr, "float32", (w, h)

    raise ValueError(f"RAW size not recognized: {size_bytes} bytes")


def to_celsius(arr, dtype_name):
    """
    Conversion:
    - int16: DJI commonly stores 10 * °C  -> °C = value / 10
    - float32: assumed already °C
    """
    if dtype_name == "int16":
        return arr.astype(np.float32) / 10.0
    return arr.astype(np.float32)


# ============================================================
# GUI
# ============================================================

class ThermalBatchGUI:
    """
    Tkinter-based graphical user interface for batch conversion of DJI thermal
    R-JPEG files to temperature TIFF rasters in degrees Celsius.
    """

    def __init__(self, root):
        """
        Creates the GUI layout, initializes Tk variables, and configures the
        conversion controls, progress bar, and log window.

        Args:
            root (tk.Tk): Root Tkinter window.
        """
        self.root = root
        root.title("DJI thermal batch temperature converter to °C")
        root.geometry("760x780")

        self._stop = False

        # --- Paths
        frame_paths = tk.LabelFrame(root, text="Paths")
        frame_paths.pack(fill="x", padx=10, pady=6)

        self.exe_path_var = tk.StringVar(value=DEFAULT_DJI_IRP)
        self.input_dir_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()

        self._add_path(frame_paths, "Path to dji_irp.exe:", self.exe_path_var, 0, self.browse_exe)
        self._add_path(frame_paths, "Input folder (R-JPEG):", self.input_dir_var, 1, self.browse_input)
        self._add_path(frame_paths, "Output folder (TIFF):", self.output_dir_var, 2, self.browse_output)

        # --- Options
        frame_opts = tk.LabelFrame(root, text="Options")
        frame_opts.pack(fill="x", padx=10, pady=6)

        self.delete_raw_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            frame_opts,
            text="Delete temporary .raw after success",
            variable=self.delete_raw_var
        ).grid(row=0, column=0, sticky="w", padx=4)

        # --- Manual parameters
        self.params = {
            "emissivity": tk.DoubleVar(value=0.95),
            "distance":   tk.DoubleVar(value=5.0),   # meters
            "ambient":    tk.DoubleVar(value=20.0),  # °C
            "humidity":   tk.DoubleVar(value=50.0),  # %
            "reflected":  tk.DoubleVar(value=20.0)   # °C
        }

        frame_manual = tk.LabelFrame(root, text="Manual parameters")
        frame_manual.pack(fill="x", padx=10, pady=6)

        r = 0
        for text, key in [
            ("Emissivity", "emissivity"),
            ("Distance (m)", "distance"),
            ("Ambient temperature (°C)", "ambient"),
            ("Relative humidity (%)", "humidity"),
            ("Reflected temperature (°C)", "reflected"),
        ]:
            tk.Label(frame_manual, text=text + ":").grid(row=r, column=0, sticky="w", padx=4, pady=2)
            tk.Entry(frame_manual, textvariable=self.params[key], width=10).grid(row=r, column=1, sticky="w", pady=2)
            r += 1

        # --- Progress
        frame_progress = tk.Frame(root)
        frame_progress.pack(fill="x", padx=10, pady=4)

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(frame_progress, variable=self.progress_var, maximum=1.0)
        self.progress_bar.pack(fill="x")

        self.progress_label = tk.Label(frame_progress, text="Waiting…")
        self.progress_label.pack(anchor="w")

        # --- Log
        frame_log = tk.LabelFrame(root, text="Log")
        frame_log.pack(fill="both", expand=True, padx=10, pady=6)

        self.log_box = scrolledtext.ScrolledText(frame_log, height=18)
        self.log_box.pack(fill="both", expand=True)

        # --- Buttons
        frame_btn = tk.Frame(root)
        frame_btn.pack(fill="x", padx=10, pady=8)

        tk.Button(
            frame_btn,
            text="Start conversion",
            bg="#4CAF50",
            fg="white",
            command=self.start_conversion
        ).pack(side="left", padx=4)

        tk.Button(frame_btn, text="Stop", command=self.stop_requested).pack(side="left", padx=4)
        tk.Button(frame_btn, text="Quit", command=root.quit).pack(side="right", padx=4)

    # ---------- thread-safe UI helpers ----------
    def ui_log(self, msg):
        """
        Schedules a log message to be appended from the main Tkinter thread.

        Args:
            msg (str): Message text to display in the log window.
        """
        self.root.after(0, lambda: self._log_now(msg))

    def _log_now(self, msg):
        """
        Appends a message to the log widget immediately.

        Args:
            msg (str): Message text to append.
        """
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")

    def ui_progress(self, value_0_1, label_text):
        """
        Updates the progress bar and its label from the Tkinter main thread.

        Args:
            value_0_1 (float): Progress value scaled from 0 to 1.
            label_text (str): Text shown next to the progress bar.
        """
        def _upd():
            self.progress_var.set(value_0_1)
            self.progress_label.config(text=label_text)
        self.root.after(0, _upd)

    def ui_info(self, title, text):
        """
        Displays an informational message box in a thread-safe way.

        Args:
            title (str): Message box title.
            text (str): Message body.
        """
        self.root.after(0, lambda: messagebox.showinfo(title, text))

    def ui_error(self, title, text):
        """
        Displays an error message box in a thread-safe way.

        Args:
            title (str): Message box title.
            text (str): Message body.
        """
        self.root.after(0, lambda: messagebox.showerror(title, text))

    # ---------- Path rows ----------
    def _add_path(self, frame, label, var, row, browse_cmd):
        """
        Adds a labelled path entry row with a browse button to the GUI.

        Args:
            frame (tk.Widget): Parent container.
            label (str): Text displayed next to the entry field.
            var (tk.StringVar): Tkinter variable bound to the entry.
            row (int): Grid row index.
            browse_cmd (callable): Callback executed when the browse button is clicked.
        """
        tk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=2)
        tk.Entry(frame, textvariable=var, width=60).grid(row=row, column=1, padx=(6, 0))
        tk.Button(frame, text="Browse", command=browse_cmd).grid(row=row, column=2, padx=6)

    def browse_exe(self):
        """Opens a file dialog and lets the user choose the dji_irp.exe file."""
        path = filedialog.askopenfilename(
            title="Choose dji_irp.exe",
            filetypes=[("Executable", "*.exe")]
        )
        if path:
            self.exe_path_var.set(path)

    def browse_input(self):
        """Opens a folder dialog and stores the selected input directory."""
        d = filedialog.askdirectory(title="Choose input folder")
        if d:
            self.input_dir_var.set(d)

    def browse_output(self):
        """Opens a folder dialog and stores the selected output directory."""
        d = filedialog.askdirectory(title="Choose output folder")
        if d:
            self.output_dir_var.set(d)

    # ---------- Controls ----------
    def stop_requested(self):
        """Requests graceful termination of the running batch conversion."""
        self._stop = True
        self.ui_log("🟥 Stop requested by user.")

    def start_conversion(self):
        """
        Validates user inputs, creates the output folder if needed, and starts
        the batch conversion in a background thread.
        """
        exe = self.exe_path_var.get().strip()
        inp = self.input_dir_var.get().strip()
        out = self.output_dir_var.get().strip()

        if not os.path.isfile(exe):
            messagebox.showerror("Error", "Invalid path to dji_irp.exe")
            return
        if not os.path.isdir(inp):
            messagebox.showerror("Error", "Choose a valid input folder")
            return

        os.makedirs(out, exist_ok=True)
        self._stop = False
        self.ui_log("▶ Starting batch…")
        Thread(target=self._worker, args=(exe, inp, out), daemon=True).start()

    def _worker(self, exe, inp, out):
        """
        Processes all JPEG files in the input folder, converts each file to a
        temporary RAW temperature image through DJI Thermal SDK, transforms it
        to a float32 Celsius TIFF, and updates the GUI log and progress widgets.

        Args:
            exe (str): Path to dji_irp.exe.
            inp (str): Input folder containing R-JPEG files.
            out (str): Output folder for TIFF rasters.
        """
        try:
            files = [f for f in os.listdir(inp) if f.lower().endswith((".jpg", ".jpeg"))]
            files.sort()
            total = len(files)

            if total == 0:
                self.ui_info("Info", "No R-JPEG files found.")
                return

            param_values = {k: v.get() for k, v in self.params.items()}

            for i, fname in enumerate(files, start=1):
                if self._stop:
                    self.ui_log("⏹ Stopped by user.")
                    break

                in_path = os.path.join(inp, fname)
                base = os.path.splitext(fname)[0]
                tmp_raw = os.path.join(tempfile.gettempdir(), f"__{base}.raw")

                rc, outtxt, cmd = call_dji_irp_measure(exe, in_path, tmp_raw, param_values)

                if rc != 0 or not os.path.exists(tmp_raw):
                    self.ui_log(f"❌ {fname} failed (code {rc})")
                    self.ui_log("CMD: " + " ".join(cmd))
                    if outtxt.strip():
                        self.ui_log(outtxt.strip())
                    continue

                raw_size = os.path.getsize(tmp_raw)

                try:
                    arr_raw, dtype_name, shape = read_raw_smart(tmp_raw)
                    arr_c = to_celsius(arr_raw, dtype_name)
                except Exception as e:
                    self.ui_log(f"❌ {fname} RAW read/convert failed: {e}")
                    self.ui_log(f"RAW size: {raw_size} bytes")
                    continue

                out_tiff = os.path.join(out, base + ".tiff")
                tifffile.imwrite(out_tiff, arr_c.astype(np.float32))

                self.ui_log(
                    f"✅ {fname} → {out_tiff} | RAW={raw_size}B | dtype={dtype_name} | shape={shape[0]}x{shape[1]} | "
                    f"{np.nanmin(arr_c):.1f}°C .. {np.nanmax(arr_c):.1f}°C"
                )

                if self.delete_raw_var.get():
                    try:
                        os.remove(tmp_raw)
                    except Exception:
                        pass

                self.ui_progress(i / total, f"{i}/{total} done")

            self.ui_info("Done", "Batch complete.")

        except Exception:
            self.ui_log("💥 Fatal error:\n" + traceback.format_exc())
            self.ui_error("Error", "Batch crashed. See log.")


def main():
    """Launches the Tkinter GUI application."""
    root = tk.Tk()
    app = ThermalBatchGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
