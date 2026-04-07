# =============================================================================
# File:         vignetting_r.R
# Project:      Master's thesis – Verification of Spectral, Radiometric, and
#               Geometric Properties of DJI Mavic 3M, Matrice 4E, and
#               Matrice 4T Devices
# Author:       Martin KRUPIČKA
# Date:         2026-02-04
# Version:      1.0.0
#
# Description:
#   Load profile CSV files produced by vignetting_analysis.py, compute
#   vignetting metrics from the MEDIAN profile, and export smoothed profile
#   plots for individual profile directions.
#
# Inputs:
#   - output_folder: directory containing profile CSV files
#     (e.g. profiles_H.csv, profiles_V.csv, profiles_D1.csv, profiles_D2.csv)
#
# Outputs:
#   - profile_plot_<DIR>.png
#   - vignetting_metrics.csv
#
# Dependencies:
#   - ggplot2
#   - dplyr
#   - tidyr
#   - stringr
#   - zoo
#   - readr
#
# Run:
#   Open in RStudio and run the script (path in 'output_folder' must exist andcontain exported profile CSV files).
#
# Notes:
#   Vignetting metrics are computed from RAW (non-smoothed) MEDIAN profile
#   values so that edge pixels are not lost due to rolling-window smoothing.
#   Smoothing is applied only for visualization of the min-max envelope and
#   median profile line.
#
#   Computed metrics:
#     center_value        = mean of the central 10 % of the profile
#     edge_mean           = mean of the outer 5 % on each side
#     vignetting_drop_abs = center_value - edge_mean
#     vignetting_drop_pct = (center_value - edge_mean) / center_value * 100
#
# =============================================================================

library(ggplot2)
library(dplyr)
library(tidyr)
library(stringr)
library(zoo)
library(readr)

# =========================================================
# Output folder path
# =========================================================
output_folder <- "D:/DP/250908_chomoutovska_bc_data/260318_krupicka/260318_krupicka/M3M/DJI_202603181354_015/NIR/vystupy"

# =========================================================
# Locate profile CSV files
# =========================================================
csv_files <- list.files(
    output_folder,
    pattern    = "profiles.*\\.csv$",
    full.names = TRUE,
    recursive  = TRUE
)

if (length(csv_files) == 0) {
    stop("No CSV files containing 'profiles' were found in the output folder.")
}

# =========================================================
# Helper: vignetting metrics from the MEDIAN profile
#
#   Uses RAW (non-smoothed) values so that no edge pixels
#   are lost to rolling-window NAs.
#
#   C = indices of the central 10 % (positions 45 %–55 %)
#   E = indices of the outer  5 % on each side
# =========================================================
compute_vignetting_metrics <- function(median_long, dir_label, file_name) {
    
    median_long <- median_long %>% arrange(position)
    y    <- median_long$value          # raw DN values – never smoothed here
    npos <- length(y)
    
    # Minimum number of points needed for reliable estimates
    if (npos < 20 || sum(!is.na(y)) < 10) {
        message("  Skipping metrics – profile too short or too many NAs.")
        return(data.frame(
            file                = file_name,
            direction           = dir_label,
            n_total             = npos,
            n_center            = NA_integer_,
            n_edge              = NA_integer_,
            center_value        = NA_real_,
            edge_mean           = NA_real_,
            vignetting_drop_abs = NA_real_,
            vignetting_drop_pct = NA_real_
        ))
    }
    
    # ---------------------------------------------------------
    # Define index sets C and E  (1-based, clipped to [1, npos])
    # ---------------------------------------------------------
    # Center: middle 10 % of the profile (positions 45 %–55 %)
    c_start <- max(1L,   as.integer(floor(npos * 0.45)) + 1L)
    c_end   <- min(npos, as.integer(ceiling(npos * 0.55)))
    
    # Edges: first 5 % and last 5 % (at least 2 pixels per side)
    edge_k  <- max(2L, as.integer(floor(npos * 0.05)))
    e_left  <- 1L:edge_k
    e_right <- (npos - edge_k + 1L):npos
    
    center_vals <- y[c_start:c_end]
    edge_vals   <- c(y[e_left], y[e_right])
    
    # Drop NAs (can occur when source CSV has missing values)
    center_vals <- center_vals[!is.na(center_vals)]
    edge_vals   <- edge_vals[!is.na(edge_vals)]
    
    if (length(center_vals) == 0 || length(edge_vals) == 0) {
        warning(paste("  Metrics skipped for", file_name,
                      "– center or edge region is entirely NA."))
        return(data.frame(
            file                = file_name,
            direction           = dir_label,
            n_total             = npos,
            n_center            = NA_integer_,
            n_edge              = NA_integer_,
            center_value        = NA_real_,
            edge_mean           = NA_real_,
            vignetting_drop_abs = NA_real_,
            vignetting_drop_pct = NA_real_
        ))
    }
    
    # ---------------------------------------------------------
    # Equations
    # ---------------------------------------------------------
    center_value        <- mean(center_vals)                          
    edge_mean           <- mean(edge_vals)                            
    vignetting_drop_abs <- center_value - edge_mean                   
    vignetting_drop_pct <- if (abs(center_value) > 1e-9)             
        (vignetting_drop_abs / center_value) * 100
    else NA_real_
    
    data.frame(
        file                = file_name,
        direction           = dir_label,
        n_total             = npos,
        n_center            = length(center_vals),   # |C|
        n_edge              = length(edge_vals),      # |E|
        center_value        = round(center_value,        4),
        edge_mean           = round(edge_mean,            4),
        vignetting_drop_abs = round(vignetting_drop_abs,  4),
        vignetting_drop_pct = round(vignetting_drop_pct,  4)
    )
}

# =========================================================
# Main loop
# =========================================================
all_metrics <- list()

for (profile_file in csv_files) {
    
    dir_match <- str_match(basename(profile_file), "profiles?_([A-Za-z0-9]+)\\.csv$")
    dir_label <- ifelse(!is.na(dir_match[, 2]), dir_match[, 2], "unknown")
    
    message(paste("Processing:", basename(profile_file), "-> direction:", dir_label))
    
    df <- read.csv(profile_file, check.names = FALSE)
    
    if (!"image" %in% names(df)) {
        warning(paste("File", basename(profile_file), "has no 'image' column – skipped."))
        next
    }
    
    median_row <- df %>% filter(image == "MEDIAN")
    df_slices  <- df %>% filter(image != "MEDIAN")
    
    if (nrow(median_row) == 0) {
        warning(paste("File", basename(profile_file), "has no MEDIAN row – skipped."))
        next
    }
    
    # Long format – individual images
    df_long <- df_slices %>%
        pivot_longer(-image, names_to = "position", values_to = "value") %>%
        mutate(position = as.numeric(sub("p", "", position)))
    
    # Long format – median (raw values used for metrics below)
    median_long <- median_row %>%
        pivot_longer(-image, names_to = "position", values_to = "value") %>%
        mutate(position = as.numeric(sub("p", "", position)))
    
    # Per-position min/max envelope (smoothed for plotting only)
    range_df <- df_long %>%
        group_by(position) %>%
        summarise(
            min_val = min(value, na.rm = TRUE),
            max_val = max(value, na.rm = TRUE),
            .groups = "drop"
        ) %>%
        mutate(
            min_val_smooth = zoo::rollmean(min_val, k = 15, fill = NA, align = "center"),
            max_val_smooth = zoo::rollmean(max_val, k = 15, fill = NA, align = "center")
        )
    
    # Smooth median for plotting only – raw $value column is kept intact
    median_long <- median_long %>%
        mutate(value_smooth = zoo::rollmean(value, k = 15, fill = NA, align = "center"))
    
    # ---------------------------------------------------
    # Compute metrics (eqs. 21–24) using RAW median values
    # ---------------------------------------------------
    metrics_row <- compute_vignetting_metrics(
        median_long = median_long,
        dir_label   = dir_label,
        file_name   = basename(profile_file)
    )
    all_metrics[[length(all_metrics) + 1]] <- metrics_row
    
    message(sprintf(
        "  center=%.2f  edge=%.2f  drop_abs=%.2f  drop_pct=%.2f %%  |C|=%s  |E|=%s",
        metrics_row$center_value,
        metrics_row$edge_mean,
        metrics_row$vignetting_drop_abs,
        metrics_row$vignetting_drop_pct,
        metrics_row$n_center,
        metrics_row$n_edge
    ))
    
    # ---------------------------------------------------
    # Plot: smoothed ribbon + smoothed median line
    # ---------------------------------------------------
    p <- ggplot() +
        geom_ribbon(
            data = range_df,
            aes(x = position, ymin = min_val_smooth, ymax = max_val_smooth),
            fill = "lightblue", alpha = 0.5
        ) +
        geom_line(
            data = median_long,
            aes(x = position, y = value_smooth),
            color = "red", linewidth = 1
        ) +
        labs(
            title    = paste("Profil vinětce -", dir_label),
            subtitle = "Měřený na DJI Mavic 3M pro pásmo NIR",
            x        = "Pozice (px)",
            y        = "DN hodnota"
        ) +
        theme_minimal(base_size = 9) +
        theme(
            legend.position     = "none",
            plot.title.position = "plot",
            plot.title    = element_text(face = "bold", size = 10, hjust = 0.5,
                                         margin = margin(b = 3)),
            plot.subtitle = element_text(size = 8, hjust = 0.5, color = "gray30",
                                         margin = margin(b = 5)),
            axis.title    = element_text(size = 8),
            axis.text     = element_text(size = 7),
            text          = element_text(size = 9)
        )
    
    print(p)
    
    ggsave(
        filename = file.path(output_folder, paste0("profile_plot_", dir_label, ".png")),
        plot     = p,
        width    = 8,
        height   = 4,
        dpi      = 300
    )
}

# =========================================================
# Save combined metrics table
# =========================================================
metrics_df <- bind_rows(all_metrics)
out_csv    <- file.path(output_folder, "vignetting_metrics.csv")
write_csv(metrics_df, out_csv)

message("\nDone! Plots saved to:  ", output_folder)
message("Metrics saved to:       ", out_csv)
message("\nMetrics preview:")
print(metrics_df)