# Modelled data: regional stacking-ensemble monthly discharge model.
# Data: PUBLISHED/data/case-studies/regional_discharge_data.csv,
#       PUBLISHED/data/case-studies/regional_discharge_gauge_skill.csv,
#       PUBLISHED/data/case-studies/regional_discharge_predictions.csv
# Paper-02 reference: Section 2.4.2.
#
# Run: Rscript ANALYSIS_R/modelled/10_regional_discharge_ensemble.R

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

feature_table <- read_csv(data_path("case-studies", "regional_discharge_data.csv"), show_col_types = FALSE)
gauge_skill <- read_csv(data_path("case-studies", "regional_discharge_gauge_skill.csv"), show_col_types = FALSE)
predictions <- read_csv(data_path("case-studies", "regional_discharge_predictions.csv"), show_col_types = FALSE)

qc_summary(feature_table, "Assembled feature table (all candidate gauges)")
check_count(nrow(feature_table), 59516, "assembled monthly records")
check_count(n_distinct(feature_table$gauge_code), 114, "unique gauges in the assembled table")

qc_summary(gauge_skill, "Per-gauge skill (trained, quality-screened model)")
check_count(nrow(gauge_skill), 38, "gauges in the trained/reported model")
check_count(sum(gauge_skill$records), 6739, "total monthly records across trained gauges")

header("Median vs. mean skill (recomputed from the released per-gauge table)")
cat(sprintf("  Median R^2  = %.4f  (paper-02 states 0.8572)\n", median(gauge_skill$r2, na.rm = TRUE)))
cat(sprintf("  Mean R^2    = %.4f  (paper-02 states -1.5898)\n", mean(gauge_skill$r2, na.rm = TRUE)))
cat(sprintf("  Median RMSE = %.2f m3/s (paper-02 states 7.97 m3/s)\n", median(gauge_skill$rmse, na.rm = TRUE)))
cat(sprintf("  Median rel. RMSE = %.1f%% (paper-02 states 43.6%%)\n",
            median(gauge_skill$rel_rmse_pct, na.rm = TRUE)))
cat(sprintf("  Median correlation = %.4f (paper-02 states 0.9276)\n",
            median(gauge_skill$correlation, na.rm = TRUE)))
cat("\nThe median/mean gap is real, not a reporting artefact: a minority of gauges\n",
    "fit very badly and drag the mean far below zero. See the skill-distribution\n",
    "breakdown below for which gauges those are.\n")

header("Skill-distribution breakdown")
gauge_skill <- gauge_skill %>%
  mutate(skill_band = case_when(
    r2 > 0.70 ~ "high (R2 > 0.70)",
    r2 >= 0.60 ~ "good (0.60-0.70)",
    r2 >= 0.50 ~ "moderate (0.50-0.60)",
    TRUE ~ "low (R2 < 0.50)"
  ))
band_counts <- gauge_skill %>% count(skill_band) %>% mutate(pct = round(100 * n / sum(n), 1))
print(as.data.frame(band_counts))
cat("Paper-02 states: high 24 (63.2%), good 0 (0.0%), moderate 3 (7.9%), low 11 (28.9%).\n")

header("Skill by glacier-fraction stratum (basin type)")
gauge_skill <- gauge_skill %>%
  mutate(glacier_band = case_when(
    glacier_pct > 10 ~ "glacial-dominated (>10%)",
    glacier_pct >= 5 ~ "snow-dominated (5-10%)",
    TRUE ~ "rain-dominated (<5%)"
  ))
strata <- gauge_skill %>% group_by(glacier_band) %>%
  summarise(n_gauges = n(), median_r2 = median(r2, na.rm = TRUE), .groups = "drop")
print(as.data.frame(strata))
cat("A stratum with very few gauges produces an unstable or NA median -- exactly\n",
    "what the published case-study report itself notes for the glacial and\n",
    "snow-dominated strata.\n")

header("Feature-importance sanity check (worst- and best-fit gauges)")
worst <- gauge_skill %>% arrange(r2) %>% slice_head(n = 5) %>%
  select(gauge_code, r2, rmse, records, area_km2, glacier_pct)
best <- gauge_skill %>% arrange(desc(r2)) %>% slice_head(n = 5) %>%
  select(gauge_code, r2, rmse, records, area_km2, glacier_pct)
cat("Five worst-fit gauges:\n"); print(as.data.frame(worst))
cat("\nFive best-fit gauges:\n"); print(as.data.frame(best))

qc_summary(predictions, "Monthly predictions vs. observed (all trained gauges)", save_csv = FALSE)
