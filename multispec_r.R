# =============================================================================
# File:         multispec_r.R
# Project:      Master's thesis – Verification of Spectral, Radiometric, and
#               Geometric Properties of DJI Mavic 3M, Matrice 4E, and
#               Matrice 4T Devices
# Author:       Martin KRUPIČKA
# Date:         2026-04-04
# Version:      1.0.0
#
# Description:
#   Load UAV multispectral reflectance rasters for multiple flight altitudes
#   (40 m / 80 m / 120 m) and ASD spectrometer reference data, compute
#   plot-level accuracy metrics, and export boxplots per plot and band.
#
# Inputs:
#   - dirs: list of folders with per-plot reflectance rasters for each flight altitude
#   - bands: evaluated spectral bands (G, R, RE, NIR)
#   - asd_dir: folder with ASD CSV/TXT reference files
#
# Outputs:
#   - metrics_vs_ASD_per_height_median.csv
#   - metrics_vs_ASD_overall_median.csv
#   - PNG boxplots per plot and band saved into output_dir/<band>/
#
# Dependencies:
#   - terra
#   - ggplot2
#   - dplyr
#   - stringr
#   - readr
#   - tools
#   - tidyr
#
# Run:
#   Open in RStudio and run the script (paths in 'dirs' and 'asd_dir' must
#   exist).
#
# Notes:
#   ASD reference values are loaded from CSV/TXT files. If column
#   'Reflectance_abs95' is present, it is preferred; otherwise column
#   'Reflectance' is used. Repeated rasters of the same plot are merged into
#   one distribution for summary statistics and boxplots.
#
# =============================================================================

library(terra)
library(ggplot2)
library(dplyr)
library(stringr)
library(readr)
library(tools)
library(tidyr)

# =========================================================
# 1) Input folders (flight altitudes)
# =========================================================
dirs <- list(
    "40m"  = "Put/Your/Multispec/40m/Here",
    "80m"  = "Put/Your/Multispec/80m/Here",
    "120m" = "Put/Your/Multispec/120m/Here"
)

bands <- c("G", "R", "RE", "NIR")

# =========================================================
# 2) ASD folder (files can be in subfolders too)
# =========================================================
asd_dir <- "Put/Your/ASD/Abs95/Here"
ASD_LABEL <- "0.25m (ASD)" # <-- CHANGE THIS if you want a different label for the ASD reference in plots and metrics

# =========================================================
# 3) Output folder
# =========================================================
output_dir <- "Put/Your/Output/Here"
dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

for (b in bands) {
    b_clean <- gsub("[^A-Za-z0-9_-]", "", b)
    dir.create(file.path(output_dir, b_clean), showWarnings = FALSE, recursive = TRUE)
}

# =========================================================
# 0) PRE-FLIGHT CHECKS (paths + structure)
# =========================================================
dir_paths <- unlist(dirs, use.names = TRUE)
if (!is.character(dir_paths)) stop("❌ 'dirs' must contain character.")
if (any(is.na(dir_paths)) || any(!nzchar(dir_paths))) {
    stop("❌ In 'dirs' does not contain data:\n", paste(dir_paths, collapse = "\n"))
}

exists_vec <- dir.exists(dir_paths)
missing_dirs <- names(dir_paths)[!exists_vec]
if (length(missing_dirs) > 0) {
    stop(
        "❌ Missing folders: ", paste(missing_dirs, collapse = ", "), "\n",
        "Check routes:\n", paste(dir_paths[!exists_vec], collapse = "\n")
    )
}
if (!dir.exists(asd_dir)) stop("❌ asd_dir does not exist: ", asd_dir)

for (h in names(dirs)) {
    for (b in bands) {
        band_folder <- file.path(dirs[[h]], b)
        if (!dir.exists(band_folder)) {
            warning("⚠️ Missing folder for band ", b, " and height ", h, ": ", band_folder)
        }
    }
}

# =========================================================
# 4) Extract plot ID from TIFF filename
#    Example: "ASF_1" -> "ASF", "ASF_2" -> "ASF", "ASF_3" -> "ASF"
#    This ensures that repeated images are merged into one plot identifier
# =========================================================
# Parses a TIFF filename and returns the shared plot identifier used
# to merge repeated rasters of the same surface into one distribution.
parse_plot_from_tif <- function(fname_no_ext) {
    parts <- str_split(fname_no_ext, "_", simplify = TRUE)
    parts[1]
}

# =========================================================
# 5) Read raster TIFFs and MERGE all pixels from multiple
#    rasters of the same surface (altitude × band)
# =========================================================
# Reads all TIFF rasters for one height-band combination, extracts all
# valid pixel values, and merges repeated rasters belonging to the same plot.
read_band_tiffs <- function(height_folder, height_label, band_label) {
    band_folder <- file.path(height_folder, band_label)
    if (!dir.exists(band_folder)) return(NULL)
    
    files <- list.files(
        band_folder,
        pattern = "\\.tif$",
        full.names = TRUE,
        ignore.case = TRUE
    )
    if (length(files) == 0) return(NULL)
    
    cat("📁 Loading", length(files), "raster(s) from:", band_folder, "\n")
    
    # Merge all pixels from all rasters into a single data frame
    all_pixel_values <- list()
    
    for (f in files) {
        r <- tryCatch(terra::rast(f), error = function(e) NULL)
        if (is.null(r)) {
            warning("⚠️ Cannot load raster: ", f)
            next
        }
        
        # Extract all pixel values from the current raster
        vals <- tryCatch(terra::values(r, na.rm = TRUE), error = function(e) NULL)
        if (is.null(vals) || length(vals) == 0) {
            warning("⚠️ No values in raster: ", f)
            next
        }
        
        vals <- as.numeric(vals)
        vals <- vals[is.finite(vals)]  # Remove NA and infinite values
        
        if (length(vals) == 0) next
        
        # Derive the plot ID (for example, "ASF" from ASF_1.tif, ASF_2.tif, ASF_3.tif)
        base_no_ext <- tools::file_path_sans_ext(basename(f))
        plot_id <- parse_plot_from_tif(base_no_ext)
        
        cat("  ✅", basename(f), "-> plot:", plot_id, "| pixels:", length(vals), "\n")
        
        # Store all pixel values together with the matching plot ID
        all_pixel_values[[length(all_pixel_values) + 1]] <- data.frame(
            value  = vals,
            plot   = plot_id,
            height = height_label,
            band   = band_label,
            source = "Raster",
            stringsAsFactors = FALSE
        )
    }
    
    # Combine all raster pixel tables into one data frame
    # Pixels with the same plot ID will automatically form one shared boxplot
    result <- bind_rows(all_pixel_values)
    
    if (nrow(result) > 0) {
        # Print a summary showing the number of pixels per plot
        summary_counts <- result %>%
            group_by(plot) %>%
            summarise(total_pixels = n(), .groups = "drop")
        
        cat("📊 Summary for", height_label, "-", band_label, ":\n")
        for (i in 1:nrow(summary_counts)) {
            cat("   Plot", summary_counts$plot[i], ":", 
                summary_counts$total_pixels[i], "pixels (merged from all rasters)\n")
        }
    }
    
    return(result)
}

cat("🚀 Starting raster loading...\n")

raster_data <- bind_rows(lapply(names(dirs), function(h) {
    cat("\n=== Processing height:", h, "===\n")
    bind_rows(lapply(bands, function(b) {
        read_band_tiffs(dirs[[h]], h, b)
    }))
})) %>%
    na.omit() %>%
    mutate(
        height = factor(height, levels = c("40m", "80m", "120m")),
        band   = factor(band, levels = bands)
    )

if (nrow(raster_data) == 0) {
    stop("❌ No raster data loaded. Check structure: 40m/80m/120m + G/R/RE/NIR + .tif files.")
}

cat("\n✅ Total pixels loaded:", nrow(raster_data), "\n")
cat("📊 Pixels per plot/band/height:\n")
print(raster_data %>% 
    group_by(plot, band, height) %>% 
    summarise(n_pixels = n(), .groups = "drop") %>%
    arrange(plot, band, height))

# =========================================================
# 6) ASD loading 
# =========================================================
# Reads ASD tables with automatic delimiter fallback for comma, semicolon,
# and tab-separated formats.
smart_read <- function(path) {
    df <- suppressWarnings(tryCatch(readr::read_csv(path, show_col_types = FALSE), error = function(e) NULL))
    if (!is.null(df) && ncol(df) >= 2) return(df)
    
    df2 <- suppressWarnings(tryCatch(readr::read_delim(path, delim = ";", show_col_types = FALSE), error = function(e) NULL))
    if (!is.null(df2) && ncol(df2) >= 2) return(df2)
    
    df3 <- suppressWarnings(tryCatch(readr::read_delim(path, delim = "\t", show_col_types = FALSE), error = function(e) NULL))
    if (!is.null(df3) && ncol(df3) >= 2) return(df3)
    
    return(NULL)
}

# Detects the spectral band label from the ASD filename.
detect_band_from_name <- function(fname_no_ext) {
    n <- tolower(fname_no_ext)
    
    if (str_detect(n, "(^|[_\\-])nir($|[_\\-])")) return("NIR")
    if (str_detect(n, "rededge") || str_detect(n, "(^|[_\\-])re($|[_\\-])")) return("RE")
    if (str_detect(n, "(^|[_\\-])r($|[_\\-])") || str_detect(n, "(^|[_\\-])red($|[_\\-])")) return("R")
    if (str_detect(n, "(^|[_\\-])g($|[_\\-])") || str_detect(n, "(^|[_\\-])green($|[_\\-])")) return("G")
    
    return(NA_character_)
}

# Removes the band token from the ASD filename to recover the plot ID.
remove_band_token_from_name <- function(fname_no_ext) {
    x <- fname_no_ext
    x <- str_replace_all(x, "(?i)(^|[_\\-])(nir|rededge|re|red|r|green|g)($|[_\\-])", "_")
    x <- str_replace_all(x, "__+", "_")
    x <- str_replace_all(x, "^_+|_+$", "")
    x
}

cat("\n🔍 Loading ASD reference data...\n")

asd_files <- list.files(
    asd_dir,
    pattern = "\\.(csv|txt)$",
    full.names = TRUE,
    recursive = TRUE,
    ignore.case = TRUE
)
if (length(asd_files) == 0) stop("❌ No ASD files found. Check 'asd_dir' path: ", asd_dir)

cat("📁 Found", length(asd_files), "ASD files\n")

asd_data_list <- lapply(asd_files, function(f) {
    name_no_ext <- tools::file_path_sans_ext(basename(f))
    
    # Band from filename, e.g. ASF_g_abs95 -> G
    band_name <- detect_band_from_name(name_no_ext)
    if (is.na(band_name)) return(NULL)
    
    # Plot ID from filename without band token
    plot_id <- remove_band_token_from_name(name_no_ext)
    plot_id <- str_replace(plot_id, "(?i)_abs95$", "")
    if (plot_id == "") return(NULL)
    
    df <- smart_read(f)
    if (is.null(df)) return(NULL)
    
    names(df) <- str_trim(names(df))
    
    # Required ASD table structure
    if (!"Source" %in% names(df)) return(NULL)
    
    # Prefer corrected reflectance; otherwise fall back to the original values
    refl_col <- NULL
    if ("Reflectance_abs95" %in% names(df)) {
        refl_col <- "Reflectance_abs95"
    } else if ("Reflectance" %in% names(df)) {
        refl_col <- "Reflectance"
    } else {
        return(NULL)
    }
    
    vals <- suppressWarnings(as.numeric(df[[refl_col]]))
    srcs <- as.character(df$Source)
    
    keep <- is.finite(vals) & !is.na(srcs) & nzchar(srcs)
    if (!any(keep)) return(NULL)
    
    cat("  ✅", basename(f), "-> plot:", plot_id, "| band:", band_name, "| points:", sum(keep), "\n")
    
    data.frame(
        value      = vals[keep],
        plot       = plot_id,
        height     = ASD_LABEL,
        band       = band_name,
        source     = srcs[keep],
        stringsAsFactors = FALSE
    )
})

asd_data <- bind_rows(asd_data_list)
if (nrow(asd_data) == 0) {
    stop("❌ No ASD data loaded (check new CSV structure: Source + Reflectance_abs95/Reflectance).")
}

asd_data <- asd_data %>%
    mutate(
        height = factor(height, levels = c("40m", "80m", "120m", ASD_LABEL)),
        band   = factor(band, levels = bands)
    )

cat("✅ ASD data loaded:", nrow(asd_data), "measurements\n")

# =========================================================
# 7) ASD reference per plot × band
# =========================================================
asd_ref <- asd_data %>%
    group_by(plot, band) %>%
    summarise(
        ASD_n      = n(),
        ASD_median = median(value, na.rm = TRUE),
        ASD_sd     = sd(value, na.rm = TRUE),
        ASD_Q1     = as.numeric(quantile(value, 0.25, na.rm = TRUE, type = 7)),
        ASD_Q3     = as.numeric(quantile(value, 0.75, na.rm = TRUE, type = 7)),
        ASD_IQR    = ASD_Q3 - ASD_Q1,
        .groups = "drop"
    )

# =========================================================
# 8) Raster summary per plot × band × height
#    All pixels from all rasters sharing the same plot ID
# =========================================================
raster_summary <- raster_data %>%
    group_by(plot, band, height) %>%
    summarise(
        n_pix         = n(),
        raster_median = median(value, na.rm = TRUE),
        raster_sd     = sd(value, na.rm = TRUE),
        raster_Q1     = as.numeric(quantile(value, 0.25, na.rm = TRUE, type = 7)),
        raster_Q3     = as.numeric(quantile(value, 0.75, na.rm = TRUE, type = 7)),
        raster_IQR    = raster_Q3 - raster_Q1,
        .groups = "drop"
    )

cat("\n📊 Raster summary (merged pixels):\n")
print(raster_summary)

# =========================================================
# 9) Metrics vs ASD per height
# =========================================================
metrics_per_height <- raster_summary %>%
    left_join(asd_ref, by = c("plot", "band")) %>%
    filter(!is.na(ASD_median)) %>%
    mutate(
        bias_median     = raster_median - ASD_median,
        abs_err_median  = abs(raster_median - ASD_median),
        sq_err_median   = (raster_median - ASD_median)^2
    )

# =========================================================
# 10) Overall metrics across heights 40/80/120
# =========================================================
metrics_overall <- metrics_per_height %>%
    filter(height %in% c("40m", "80m", "120m")) %>%
    group_by(plot, band) %>%
    summarise(
        k               = n(),
        MAE_median      = mean(abs_err_median, na.rm = TRUE),
        RMSE_median     = sqrt(mean(sq_err_median, na.rm = TRUE)),
        AvgBias_median  = mean(bias_median, na.rm = TRUE),
        .groups = "drop"
    )

if (any(metrics_overall$k != 3)) {
    warning("⚠️ Some plot × band combinations do not contain all three heights (k != 3).")
}

cat("\n💾 Saving metrics...\n")
write_csv(metrics_per_height, file.path(output_dir, "metrics_vs_ASD_per_height_median.csv"))
write_csv(metrics_overall,    file.path(output_dir, "metrics_vs_ASD_overall_median.csv"))
cat("✅ Metrics saved\n")

# =========================================================
# 11) Merge raster + ASD for plotting
#     For plotting, ASD source is unified to one label
# =========================================================
all_data <- bind_rows(
    raster_data,
    asd_data %>% mutate(source = "ASD")
) %>%
    mutate(height = factor(height, levels = c("40m", "80m", "120m", ASD_LABEL)))

# =========================================================
# 12) Boxplots per plot × band
# =========================================================
unique_plots <- unique(all_data$plot)

cat("\n🎨 Creating boxplots...\n")

for (b in bands) {
    for (p in unique_plots) {
        
        df_bp <- all_data %>% filter(band == b, plot == p)
        if (nrow(df_bp) == 0) next
        
        st_overall <- metrics_overall %>% filter(plot == p, band == b)
        
        caption_txt <- ""
        if (nrow(st_overall) > 0) {
            caption_txt <- paste0(
                "Metriky vypočtené napříč výškami: ",
                "RMSE=", round(st_overall$RMSE_median[1], 4),
                ", MAE=", round(st_overall$MAE_median[1], 4),
                ", AvgBias=", round(st_overall$AvgBias_median[1], 4)
            )
        }
        
        g <- ggplot(df_bp, aes(x = height, y = value, fill = height)) +
            geom_boxplot(outlier.shape = NA, alpha = 0.7) +
            labs(
                title = paste("POROVNÁNÍ REFLEKTANCE MĚŘENÉ NA PLOŠE", p),
                subtitle = paste("v okolí studentských kolejí v Olomouci 29. 10. 2025 | pásmo:", b),
                x = "výška letu / zdroj dat",
                y = "reflektance (-)",
                caption = caption_txt
            ) +
            theme_minimal(base_size = 14) +
            theme(
                legend.position = "none",
                plot.title = element_text(face = "bold", size = 16, hjust = 0.5),
                plot.subtitle = element_text(size = 12, hjust = 0.5, color = "gray30"),
                plot.caption = element_text(size = 10, hjust = 0, color = "gray30")
            )
        
        out_name <- paste0(p, "_", b, "_boxplot_with_ASD.png")
        b_clean <- gsub("[^A-Za-z0-9_-]", "", b)
        
        ggsave(
            filename = file.path(output_dir, b_clean, out_name),
            plot = g,
            width = 10, height = 6, dpi = 300
        )
        
        cat("✅ Saved plot:", p, "| band:", b, "\n")
    }
}

cat("\n🎉 Done! All plots + metrics saved to:", output_dir, "\n")
cat("📊 Summary:\n")
cat("   - Pixels from multiple rasters of same surface were MERGED\n")
cat("   - Each boxplot shows distribution of ALL pixels\n")
cat("   - Metrics computed from merged pixel statistics\n")