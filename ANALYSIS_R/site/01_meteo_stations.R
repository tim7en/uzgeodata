# Site observations: meteorological station network.
# Data: PUBLISHED/data/hydroclimate/meteo-stations.geojson (+ manifest)
# Paper-02 reference: Section 2.1.1.
#
# Run: Rscript ANALYSIS_R/site/01_meteo_stations.R

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

stations <- read_geojson_properties(data_path("hydroclimate", "meteo-stations.geojson"))
manifest <- fromJSON(data_path("hydroclimate", "meteo-stations.manifest.json"))

stations <- stations %>%
  mutate(across(c(elevation_m, observations, first_year, last_year,
                   recorded_air_c, reanalysis_air_c, residual_c), as.numeric))

qc_summary(stations, "Meteorological stations")

header("Cross-checks against paper-02 / manifest")
check_count(nrow(stations), manifest$stations, "total station count")
check_count(sum(stations$archive == "national", na.rm = TRUE),
            manifest$by_archive$national, "national-archive stations")
check_count(sum(stations$archive == "nsidc", na.rm = TRUE),
            manifest$by_archive$nsidc, "NSIDC-archive stations")
check_count(sum(stations$elevation_m > 1500, na.rm = TRUE),
            manifest$above_1500m, "stations above 1,500 m")

cat(sprintf("\nElevation range in file: %.1f - %.1f m (manifest: %.1f - %.1f m)\n",
            min(stations$elevation_m, na.rm = TRUE), max(stations$elevation_m, na.rm = TRUE),
            manifest$elevation_m$min, manifest$elevation_m$max))
cat(sprintf("Sum of per-station 'observations' column: %s (manifest total: %s)\n",
            format(sum(stations$observations, na.rm = TRUE), big.mark = ","),
            format(manifest$observations, big.mark = ",")))

header("Measure coverage (station counts by measured variable)")
measure_counts <- table(unlist(strsplit(stations$measures, ",\\s*")))
print(measure_counts)
cat("Manifest by_measure:\n")
str(manifest$by_measure)

header("Placement-status breakdown (name-matched vs source-declared coordinate)")
print(table(stations$archive, stations$placement_status, useNA = "ifany"))

header("Reanalysis-vs-recorded residual (recorded_air_c - reanalysis_air_c)")
resid_summary <- summary(stations$residual_c)
print(resid_summary)
cat("A large |residual| flags a station worth re-checking for a coordinate or\n",
    "unit problem; this script does not resolve any such case, only surfaces it.\n")
