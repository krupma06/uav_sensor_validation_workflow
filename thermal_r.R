# =============================================================================
# File:         thermal_r.R
# Project:      Master's thesis – Verification of Spectral, Radiometric, and Geometric Properties of DJI Mavic 3M,    Matrice 4E, and Matrice 4T Devices
# Author:       Martin KRUPIČKA
# Date:         2026-02-04
# Version:      1.0.0
#
# Description:
#   Load UAV thermal temperature rasters for multiple flight altitudes and a
#   FLIR reference raster, compute plot-level accuracy metrics
#   (bias/MAE/RMSE), and export boxplots per plot; optionally adds a single
#   contact thermometer point for a selected plot.
#
# Inputs:
#   - dirs: list of folders with per-plot temperature GeoTIFFs (40m/80m/120m + FLIR_median)
#   - Optional: contact thermometer value (single point) added for a chosen plot
#
# Outputs:
#   - thermal_stats_short.csv (plot-level metrics)
#   - PNG boxplots per plot saved to output_dir
#
# Dependencies:
#   - terra
#   - ggplot2
#   - dplyr
#   - stringr
#   - readr
#   - tools
#
# Run:
#   Open in RStudio and run the script (paths in 'dirs' must exist).
#
# Notes:
#   FLIR reference label is renamed for plotting and used as plot-level
#   reference for metrics.
#
# =============================================================================


library(terra)
library(ggplot2)
library(dplyr)
library(stringr)
library(readr)
library(tools)

# --------------------------
# 1) Folder paths
# --------------------------
dirs <- list(
    "40m"         = "Put/Your/Thermal/40m/Here", # <-- CHANGE THIS to your 40m folder path
    "80m"         = "Put/Your/Thermal/80m/Here", # <-- CHANGE THIS to your 80m folder path
    "120m"        = "Put/Your/Thermal/120m/Here", # <-- CHANGE THIS to your 120m folder path
    "FLIR_median" = "Put/Your/Thermal/FLIR_median/Here" # <-- CHANGE THIS to your FLIR_median folder path
)

# --------------------------
# 2) Labels
# --------------------------
FLIR_LABEL <- "1.5m (FLIR)" # <-- CHANGE THIS if you want a different label for the FLIR reference in plots
KONTAKTNI_LABEL <- "kontaktní teploměr" # <-- CHANGE THIS if you want a different label for the contact thermometer point in plots

VOD_PLOCHA <- "VOD"
kontaktni_temp <- 21.8 # <-- CHANGE THIS to the contact thermometer value you want to add (single point) – make sure to also update the label above if needed

# --------------------------
# 0) Pre-flight checks
# --------------------------
dir_paths <- unlist(dirs, use.names = TRUE)
if (any(is.na(dir_paths)) || any(!nzchar(dir_paths))) {
    stop("❌ The 'dirs' path is empty/NA:\n", paste(dir_paths, collapse = "\n"))
}
exists_vec <- dir.exists(dir_paths)
if (any(!exists_vec)) {
    stop(
        "❌ Some folders do not exist:\n",
        paste(names(dir_paths)[!exists_vec], "->", dir_paths[!exists_vec], collapse = "\n")
    )
}

# --------------------------
# 3) Function to read TIFFs from a folder
# --------------------------
# Loads all TIFF rasters from one folder, extracts pixel values, and
# returns a long table tagged by plot and acquisition height.
read_all_tiffs <- function(folder, label) {
    files <- list.files(folder, pattern = "\\.tif$", full.names = TRUE, ignore.case = TRUE)
    if (length(files) == 0) return(NULL)
    
    data_list <- lapply(files, function(f) {
        r <- tryCatch(terra::rast(f), error = function(e) NULL)
        if (is.null(r)) return(NULL)
        
        vals <- tryCatch(as.numeric(terra::values(r, na.rm = TRUE)), error = function(e) NULL)
        if (is.null(vals) || length(vals) == 0) return(NULL)
        
        fname <- basename(f)
        
        # Extract the plot ID from the filename
        # Expected FLIR pattern: FLIR_<PLOT>_median.tif
        plocha <- if (str_detect(fname, "^FLIR_")) {
            out <- str_extract(fname, "(?<=FLIR_).+?(?=_median)")
            if (is.na(out) || out == "") tools::file_path_sans_ext(fname) else out
        } else {
            tools::file_path_sans_ext(fname)
        }
        
        data.frame(
            hodnota = vals,
            plocha  = plocha,
            vyska   = label,
            stringsAsFactors = FALSE
        )
    })
    
    bind_rows(data_list)
}

# --------------------------
# 4) Load all raster data and append the optional contact reference
# --------------------------
all_data <- bind_rows(lapply(names(dirs), function(name) {
    read_all_tiffs(dirs[[name]], name)
})) %>%
    na.omit()

if (nrow(all_data) == 0) stop("❌ No data was uploaded (check the .tif files in the folders).")

all_data$vyska <- ifelse(all_data$vyska == "FLIR_median", FLIR_LABEL, all_data$vyska)

all_data <- bind_rows(
    all_data,
    data.frame(
        hodnota = kontaktni_temp,
        plocha  = VOD_PLOCHA,
        vyska   = KONTAKTNI_LABEL,
        stringsAsFactors = FALSE
    )
)

all_data$vyska <- factor(all_data$vyska, levels = c("40m", "80m", "120m", FLIR_LABEL, KONTAKTNI_LABEL))

# --------------------------
# 5) Output folder
# --------------------------
output_dir <- "Put/Your/Thermal/Graphs/Here" # <-- CHANGE THIS to your desired output folder path for graphs and CSV
dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

# ==========================================================
# 6) Plot-level summary
# ==========================================================
plot_stats <- all_data %>%
    group_by(plocha, vyska) %>%
    summarise(
        n_pix       = n(),
        median_temp = median(hodnota, na.rm = TRUE),
        sd_temp     = sd(hodnota, na.rm = TRUE),
        Q1_temp     = as.numeric(quantile(hodnota, 0.25, na.rm = TRUE, type = 7)),
        Q3_temp     = as.numeric(quantile(hodnota, 0.75, na.rm = TRUE, type = 7)),
        IQR_temp    = Q3_temp - Q1_temp,
        .groups = "drop"
    )

# ==========================================================
# 7) FLIR reference per plot
# ==========================================================
flir_ref <- plot_stats %>%
    filter(vyska == FLIR_LABEL) %>%
    transmute(
        plocha,
        FLIR_n      = n_pix,
        FLIR_median = median_temp,
        FLIR_sd     = sd_temp,
        FLIR_Q1     = Q1_temp,
        FLIR_Q3     = Q3_temp,
        FLIR_IQR    = IQR_temp
    )

# ==========================================================
# 8) UAV accuracy vs FLIR (plot-level, per height) 
# ==========================================================
metrics_per_height <- plot_stats %>%
    filter(vyska %in% c("40m", "80m", "120m")) %>%
    left_join(flir_ref, by = "plocha") %>%
    filter(!is.na(FLIR_median)) %>%
    mutate(
        bias_median     = median_temp - FLIR_median,
        abs_err_median  = abs(median_temp - FLIR_median),
        sq_err_median   = (median_temp - FLIR_median)^2
    )

if (nrow(metrics_per_height) == 0) {
    stop("❌ Metrics not generated: FLIR references for areas are likely missing (or area names do not match).")
}

# ==========================================================
# 9) Overall metrics across heights
# ==========================================================
metrics_overall <- metrics_per_height %>%
    group_by(plocha) %>%
    summarise(
        k              = n(),
        MAE_median     = mean(abs_err_median, na.rm = TRUE),
        RMSE_median    = sqrt(mean(sq_err_median, na.rm = TRUE)),
        AvgBias_median = mean(bias_median, na.rm = TRUE),
        .groups = "drop"
    )

if (any(metrics_overall$k != 3)) {
    warning("⚠️ Some combinations plocha×výška does not have all heights (k != 3).")
}

# ==========================================================
# 10) Export CSV
# ==========================================================
stats_one_csv <- bind_rows(
    metrics_per_height %>%
        transmute(
            typ = "per_height",
            plocha, vyska,
            n_pix,
            median_temp,
            sd_temp,         
            Q1_temp,         
            Q3_temp,      
            IQR_temp,        
            FLIR_median,
            FLIR_sd,         
            FLIR_Q1,         
            FLIR_Q3,         
            FLIR_IQR,        
            bias_median,
            abs_err_median,
            sq_err_median
        ),
    metrics_overall %>%
        transmute(
            typ = "overall",
            plocha,
            vyska = "overall",
            n_pix = NA_real_,
            median_temp = NA_real_,
            FLIR_median = NA_real_,
            bias_median = NA_real_,
            abs_err_median = NA_real_,
            sq_err_median = NA_real_,
            k,
            MAE_median,
            RMSE_median,
            AvgBias_median
        )
)

write_csv(stats_one_csv, file.path(output_dir, "thermal_stats_formulas_median.csv"))
cat("✅ Saved statistics:", file.path(output_dir, "thermal_stats_formulas_median.csv"), "\n")

# ==========================================================
# 11) Generate boxplots for each plot
# ==========================================================
unique_plochy <- unique(all_data$plocha)

for (p in unique_plochy) {
    df_p <- filter(all_data, plocha == p)
    
    st_overall <- metrics_overall %>% filter(plocha == p)
    caption_txt <- ""
    if (nrow(st_overall) > 0) {
        caption_txt <- paste0(
            "Metriky vypočtené napříč výškami: ",
            "RMSE=", round(st_overall$RMSE_median[1], 4),
            ", MAE=", round(st_overall$MAE_median[1], 4),
            ", AvgBias=", round(st_overall$AvgBias_median[1], 4)
        )
    }
    
    g <- ggplot(df_p, aes(x = vyska, y = hodnota)) +
        geom_boxplot(
            data = df_p %>% filter(vyska != KONTAKTNI_LABEL),
            aes(fill = vyska),
            outlier.shape = NA,
            alpha = 0.7
        ) +
        geom_point(
            data = df_p %>% filter(vyska == KONTAKTNI_LABEL),
            size = 3
        ) +
        labs(
            title = paste("POROVNÁNÍ TEPLOT MĚŘENÝCH NA PLOŠE", p),
            subtitle = "v okolí chomoutovského jezera 8. 9. 2025",
            x = "výška letu / zdroj dat",
            y = "teplota (°C)",
            caption = caption_txt
        ) +
        theme_minimal(base_size = 14) +
        theme(
            legend.position = "none",
            plot.title = element_text(face = "bold", size = 16, hjust = 0.5),
            plot.subtitle = element_text(size = 12, hjust = 0.5, color = "gray30"),
            plot.caption = element_text(size = 10, hjust = 0, color = "gray30")
        )
    
    ggsave(
        filename = file.path(output_dir, paste0(p, "_boxplot.png")),
        plot = g,
        width = 8, height = 6, dpi = 300
    )
    
    cat("✅ Saved plot for:", p, "\n")
}

cat("🎉 Done! Plots + statistics saved to:", output_dir, "\n")
