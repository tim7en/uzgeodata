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

header("Land-cover/glacier predictors: fixed 2026-09-18 (was hardcoded 0.0 for every gauge)")
placeholder_cols <- c("basin_glacier_pct", "basin_forest_pct", "basin_shrub_pct",
                       "basin_grass_pct", "basin_urban_pct", "basin_water_pct")
nonzero_now <- feature_table %>% summarise(across(all_of(placeholder_cols), ~ sum(. > 0)))
print(as.data.frame(nonzero_now))
check_count(sum(feature_table$basin_permafrost_pct != 0), 0,
            "non-zero basin_permafrost_pct rows (still a documented placeholder -- no source exists)")

qc_summary(gauge_skill, "Per-gauge skill (trained model, post land-cover-fix rebuild)")
check_count(nrow(gauge_skill), 114, "gauges in the trained/reported model")
check_count(sum(gauge_skill$records), 59516, "total monthly records across trained gauges")
cat("\nBefore the fix, this table had only 38 rows despite the same 114-gauge assembled\n",
    "table above; paper-02 SS2.4.2 flags that gauge-count change as a side effect of the\n",
    "fix that is observed but not fully traced to a single line of code.\n")

header("Median vs. mean skill (recomputed from the released per-gauge table)")
cat(sprintf("  Median R^2  = %.4f  (paper-02 states 0.607)\n", median(gauge_skill$r2, na.rm = TRUE)))
cat(sprintf("  Mean R^2    = %.4f  (paper-02 states -0.79)\n", mean(gauge_skill$r2, na.rm = TRUE)))
cat(sprintf("  Median RMSE = %.2f m3/s (paper-02 states 8.56 m3/s)\n", median(gauge_skill$rmse, na.rm = TRUE)))
cat(sprintf("  Median rel. RMSE = %.1f%% (paper-02 states 53.6%%)\n",
            median(gauge_skill$rel_rmse_pct, na.rm = TRUE)))
cat(sprintf("  Median correlation = %.4f (paper-02 states 0.8144)\n",
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
cat("Paper-02 states: high 40 (35.1%), good 19 (16.7%), moderate 12 (10.5%), low 43 (37.7%).\n")

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
cat("Paper-02 states: glacial-dominated median R2 = 0.747, snow-dominated = 0.773,\n",
    "rain-dominated = 0.555 -- all three strata are now populated (were nan/single-stratum\n",
    "before the fix, since every gauge had glacier_pct == 0). Glacial and snow-dominated\n",
    "basins score BETTER than rain-dominated ones here, the reverse of what could be said\n",
    "before the fix; reported as a fresh single-run result, not independently reproduced.\n")

header("Feature-importance sanity check (worst- and best-fit gauges)")
worst <- gauge_skill %>% arrange(r2) %>% slice_head(n = 5) %>%
  select(gauge_code, r2, rmse, records, area_km2, glacier_pct)
best <- gauge_skill %>% arrange(desc(r2)) %>% slice_head(n = 5) %>%
  select(gauge_code, r2, rmse, records, area_km2, glacier_pct)
cat("Five worst-fit gauges:\n"); print(as.data.frame(worst))
cat("\nFive best-fit gauges:\n"); print(as.data.frame(best))

qc_summary(predictions, "Monthly predictions vs. observed (all trained gauges)", save_csv = FALSE)
