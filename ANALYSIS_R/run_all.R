# Runs every per-dataset QC script in ANALYSIS_R/ in the order the datasets
# appear in docs/papers/paper-02-original-data-release.md, and reports which
# ones failed rather than stopping at the first error.
#
# Run: Rscript ANALYSIS_R/run_all.R

.script_dir <- dirname(sub("^--file=", "", commandArgs(FALSE)[grepl("^--file=", commandArgs(FALSE))]))

scripts <- c(
  "site/01_meteo_stations.R",
  "site/02_discharge_gauges.R",
  "site/03_station_gauge_network_audit.R",
  "remote/04_remote_station_extractions.R",
  "remote/05_glacier_inventories.R",
  "remote/06_infrastructure_inventories.R",
  "grid/07_regional_climate_cube.R",
  "grid/08_headwater_elevation_bands.R",
  "modelled/09_pskem_hbv_model.R",
  "modelled/10_regional_discharge_ensemble.R",
  "modelled/11_sabitov_adaptation.R"
)

results <- character(0)
for (s in scripts) {
  # normalizePath() matters here: source(..., chdir = TRUE) changes the
  # working directory to dirname(path) before running the script, and a
  # *relative* path would then be re-interpreted against that new directory
  # by anything inside the script that also inspects its own source path
  # (see .this_file in each dataset script), silently doubling the prefix.
  path <- normalizePath(file.path(.script_dir, s))
  cat("\n\n##############################################\n")
  cat("## ", s, "\n")
  cat("##############################################\n")
  ok <- tryCatch({
    # Each script is run in its own fresh environment so one dataset's
    # objects can never leak into the next dataset's checks. chdir = TRUE
    # makes getwd() equal to the script's own directory while it runs, which
    # is how each script resolves the path to _helpers.R (see .script_dir at
    # the top of every dataset script) whether it is run standalone via
    # Rscript or sourced from here.
    source(path, local = new.env(), chdir = TRUE)
    TRUE
  }, error = function(e) {
    cat("ERROR in", s, ":", conditionMessage(e), "\n")
    FALSE
  })
  results[s] <- if (ok) "OK" else "FAILED"
}

cat("\n\n================ Run summary ================\n")
for (s in names(results)) cat(sprintf("  [%s] %s\n", results[s], s))
if (any(results == "FAILED")) quit(status = 1)
