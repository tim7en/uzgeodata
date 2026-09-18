# Remote observations: Earth Engine products extracted at station coordinates
# (SRTM, MOD13Q1 NDVI, MOD11A2 LST, MOD10A1 snow fraction, ERA5-Land point
# extraction, OpenLandMap texture).
# Data: PUBLISHED/data/case-studies/regional-station-context.csv,
#       PUBLISHED/data/case-studies/regional-station-monthly.csv,
#       PUBLISHED/data/case-studies/station-product-monthly.csv
# Paper-02 reference: Section 2.2.1.
#
# Run: Rscript ANALYSIS_R/remote/04_remote_station_extractions.R

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

context <- read_csv(data_path("case-studies", "regional-station-context.csv"), show_col_types = FALSE)
monthly <- read_csv(data_path("case-studies", "regional-station-monthly.csv"), show_col_types = FALSE)
product_monthly <- read_csv(data_path("case-studies", "station-product-monthly.csv"), show_col_types = FALSE)

qc_summary(context, "Per-station remote-product context (one row per station)")
check_count(nrow(context), 86, "stations with a remote-product context row")

qc_summary(monthly, "Station-month remote/in-situ comparison table", save_csv = FALSE)
check_count(nrow(monthly), 6192, "station-month rows")

header("Per-product non-missing station counts (context table)")
product_cols <- c(era5_air_c = "ERA5 temperature", lst_day_c = "MODIS LST",
                   ndvi = "MODIS NDVI", snow_occurrence = "MODIS snow fraction",
                   soil_temperature_c = "in-situ soil temperature")
for (col in names(product_cols)) {
  n_present <- sum(!is.na(context[[col]]))
  cat(sprintf("  %-24s %3d / %d stations have a non-missing value\n",
              product_cols[col], n_present, nrow(context)))
}
cat("\nPaper-02 / regional-station-environment.md report *all-season eligible*\n",
    "counts of 86 ERA5 temperature, 10 LST, 35 NDVI and 0 snow sites -- a stricter\n",
    "three-year-per-calendar-month test this script does not reproduce. The\n",
    "non-missing counts above are a weaker, purely descriptive check.\n")

qc_summary(product_monthly, "Long-format product/station/period extraction table", save_csv = FALSE)
header("Records per product (long table)")
print(product_monthly %>% count(product, sort = TRUE))

header("Worked-example correlation: elevation vs. ERA5 temperature")
fit <- lm(era5_air_c ~ elevation_m, data = context)
cat(sprintf("n = %d, r = %.3f, slope = %.3f C/km (paper-02 cites r ~ -0.828, slope ~ -5.67 C/km)\n",
            sum(complete.cases(context$era5_air_c, context$elevation_m)),
            cor(context$era5_air_c, context$elevation_m, use = "complete.obs"),
            coef(fit)["elevation_m"] * 1000))
cat("Reported here as a descriptive fit only -- not a measured lapse rate,\n",
    "matching the explicit non-claim in the source document.\n")
