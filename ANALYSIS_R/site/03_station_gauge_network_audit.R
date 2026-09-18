# Site observations: station/gauge identity and calendar-convention audit.
# Data: PUBLISHED/data/hydroclimate/hydromet-meteo-network.csv,
#       PUBLISHED/data/hydroclimate/hydromet-gauge-network.csv
# Paper-02 reference: Section 2.1.3.
#
# Run: Rscript ANALYSIS_R/site/03_station_gauge_network_audit.R

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

meteo_net <- read_csv(data_path("hydroclimate", "hydromet-meteo-network.csv"), show_col_types = FALSE)
gauge_net <- read_csv(data_path("hydroclimate", "hydromet-gauge-network.csv"), show_col_types = FALSE)

qc_summary(meteo_net, "Meteorological network identity table")
check_count(nrow(meteo_net), 86, "meteorological sites with a unique local ID")

header("Identity-flag breakdown (deterministic local IDs vs source key)")
print(table(meteo_net$identity_flag, useNA = "ifany"))
cat("Paper-02 states 9 zero/ambiguous-key sites received deterministic local IDs.\n")

header("Coordinate provenance (name-matched vs source-declared)")
print(table(meteo_net$coordinate_flag, useNA = "ifany"))

qc_summary(gauge_net, "Gauge/canal/outlet network table")
check_count(nrow(gauge_net), 113, "gauge/canal/outlet sites")

header("Station-type breakdown (river gauges / canals / outlets)")
print(table(gauge_net$station_type, useNA = "ifany"))
cat("Paper-02 states 90 river gauges, 21 canals, two outlets.\n")

header("Coordinate CRS status and elevation flag")
print(table(gauge_net$coordinate_crs_status, useNA = "ifany"))
print(table(gauge_net$elevation_flag, useNA = "ifany"))
cat("Paper-02 states seven gauge-height sentinel values were removed, not imputed;\n",
    "an 'elevation_flag' category for that removal is expected here, not a silently\n",
    "filled elevation column.\n")
