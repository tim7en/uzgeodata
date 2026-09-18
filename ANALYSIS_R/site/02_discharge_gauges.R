# Site observations: discharge gauges (CA-discharge archive + local Pskem
# daily record).
# Data: PUBLISHED/data/research/ca-discharge-*, PUBLISHED/data/hydroclimate/pskem-discharge-daily.csv
# Paper-02 reference: Section 2.1.2.
#
# Run: Rscript ANALYSIS_R/site/02_discharge_gauges.R

.this_file <- local({
  ofiles <- Filter(Negate(is.null), lapply(sys.frames(), function(f) f$ofile))
  if (length(ofiles) > 0) return(ofiles[[length(ofiles)]])
  args <- commandArgs(FALSE)
  file_arg <- args[grepl("^--file=", args)]
  if (length(file_arg) == 1) return(sub("^--file=", "", file_arg))
  NULL
})
.script_dir <- if (!is.null(.this_file)) dirname(.this_file) else getwd()
source(file.path(.script_dir, "..", "_helpers.R"), local = TRUE)

gauges <- read_geojson_properties(data_path("research", "ca-discharge-stations.geojson")) %>%
  mutate(across(c(q_m3s, n_complete, n_miss, n_propmiss, n_largestgap), as.numeric),
         has_ts = as.logical(has_ts))
summary_json <- fromJSON(data_path("research", "ca-discharge-summary.json"))
pskem_cmp <- read_csv(data_path("research", "ca-discharge-pskem-comparison.csv"), show_col_types = FALSE)
pskem_daily <- read_csv(data_path("hydroclimate", "pskem-discharge-daily.csv"), show_col_types = FALSE)

qc_summary(gauges, "CA-discharge gauge stations")

header("Cross-checks against paper-02 / source manifest")
check_count(nrow(gauges), summary_json$counts$gauge_rows, "gauge points published")
check_count(sum(gauges$has_ts, na.rm = TRUE), summary_json$counts$gauges_with_time_series,
            "gauges with an attached time series")
cat(sprintf("Temporal coverage stated: %s to %s\n",
            summary_json$temporal_coverage$first, summary_json$temporal_coverage$last))

header("Pskem cross-validation (gauge 16290 vs local daily record)")
qc_summary(pskem_cmp, "CA-discharge/Pskem dekad comparison", save_csv = FALSE)
check_count(nrow(pskem_cmp), 555, "paired dekads")

r_recomputed <- cor(pskem_cmp$ca_discharge_cms, pskem_cmp$local_daily_dekad_mean_cms,
                     use = "complete.obs")
rmse_recomputed <- sqrt(mean(pskem_cmp$difference_cms^2, na.rm = TRUE))
bias_recomputed <- mean(pskem_cmp$difference_cms, na.rm = TRUE)
cat("\nRecomputed independently from the published CSV (not read from a manifest):\n")
cat(sprintf("  Pearson r  = %.4f  (paper-02 states 0.998)\n", r_recomputed))
cat(sprintf("  RMSE       = %.3f m3/s  (paper-02 states 0.35 m3/s)\n", rmse_recomputed))
cat(sprintf("  Mean bias  = %.3f m3/s  (paper-02 states -0.09 m3/s)\n", bias_recomputed))

header("Local Pskem daily discharge record")
pskem_daily <- pskem_daily %>% mutate(date = as.Date(sprintf("%04d-%02d-%02d", year, month, day)))
qc_summary(pskem_daily, "Local Pskem daily discharge", save_csv = FALSE)
cat(sprintf("\nDate range: %s to %s (%d days)\n",
            min(pskem_daily$date, na.rm = TRUE), max(pskem_daily$date, na.rm = TRUE),
            nrow(pskem_daily)))
cat("No manifest sidecar exists for this file (flagged as a gap in the paper-02 handoff).\n")
