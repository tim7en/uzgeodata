# Modelled data: Sabitov (2018) thesis adaptation -- four daily model
# structures re-implemented on real 2000-2017 daily forcing.
# Data: PUBLISHED/data/case-studies/sabitov-daily-predictions.csv,
#       sabitov-model-components.csv, sabitov-flow-duration.csv,
#       sabitov-monthly-trends.csv, sabitov-climate-scenarios.csv
# Paper-02 reference: Section 2.4.3.
#
# Run: Rscript ANALYSIS_R/modelled/11_sabitov_adaptation.R

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

predictions <- read_csv(data_path("case-studies", "sabitov-daily-predictions.csv"), show_col_types = FALSE)
components <- read_csv(data_path("case-studies", "sabitov-model-components.csv"), show_col_types = FALSE)
flow_duration <- read_csv(data_path("case-studies", "sabitov-flow-duration.csv"), show_col_types = FALSE)
monthly_trends <- read_csv(data_path("case-studies", "sabitov-monthly-trends.csv"), show_col_types = FALSE)
climate_scenarios <- read_csv(data_path("case-studies", "sabitov-climate-scenarios.csv"), show_col_types = FALSE)

qc_summary(predictions, "Daily predictions, Models 1-4 vs. observed")
check_count(nrow(predictions), 6575, "daily rows (2000-2017)")

header("Independently recomputed daily NSE for each of the four adapted models")
thesis_daily_nse <- c(m1 = 0.70, m2 = 0.23, m3 = 0.76, m4 = 0.29)
for (m in c("m1", "m2", "m3", "m4")) {
  ok <- is.finite(predictions$observed_cms) & is.finite(predictions[[m]])
  score <- nse(predictions$observed_cms[ok], predictions[[m]][ok])
  cat(sprintf("  %s: n = %5d, this adaptation's NSE = %7.4f  |  thesis Table 2-4 NSE = %.2f\n",
              m, sum(ok), score, thesis_daily_nse[m]))
}
cat("\nThese are two different implementations on (at best) similar but not proven\n",
    "identical forcing; paper-02 SS2.4.3 is explicit that without the original\n",
    "forcing and code, an exact numerical reproduction cannot be asserted. A large\n",
    "gap between this adaptation's NSE and the thesis figure is expected and is\n",
    "not, by itself, evidence that either implementation is wrong.\n")

qc_summary(components, "Water-balance components (adapted model internals)", save_csv = FALSE)

header("Daily water-balance closure check (component script consistency)")
closure <- components %>%
  mutate(balance_check = precipitation_mm - et_mm - runoff_mm -
           (snow_storage_mm + soil_storage_mm + groundwater_storage_mm -
              dplyr::lag(snow_storage_mm + soil_storage_mm + groundwater_storage_mm)))
cat(sprintf("Mean |balance residual| across periods (excluding first row): %.4f mm\n",
            mean(abs(closure$balance_check), na.rm = TRUE)))
cat("A residual near zero indicates storage terms and fluxes are internally\n",
    "consistent in this output; this is a bookkeeping check, not a validation of\n",
    "the underlying physics.\n")

qc_summary(flow_duration, "Flow-duration curves (by series)", save_csv = FALSE)
header("Q50/Q90/Q95 by series")
fdc_stats <- flow_duration %>%
  filter(exceedance_percent %in% c(50, 90, 95)) %>%
  arrange(series, exceedance_percent)
print(as.data.frame(fdc_stats))

qc_summary(monthly_trends, "Monthly Kendall/Sen trend diagnostics", save_csv = FALSE)
check_count(nrow(monthly_trends), 12, "calendar months with a trend estimate")
header("Months with p_holm < 0.05 (Holm-corrected significance)")
sig <- monthly_trends %>% filter(p_holm < 0.05)
if (nrow(sig) == 0) cat("None -- no calendar month survives Holm correction.\n") else print(as.data.frame(sig))

qc_summary(climate_scenarios, "Climate perturbation scenarios", save_csv = FALSE)
header("Scenario grid (temperature/precipitation/glacier-area multipliers)")
print(climate_scenarios %>% distinct(scenario, temperature_delta_c, precipitation_multiplier,
                                      glacier_area_multiplier))
