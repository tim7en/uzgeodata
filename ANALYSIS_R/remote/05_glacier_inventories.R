# Remote observations: glacier inventories (GLIMS-derived headwater outlines,
# regional point-centre catalogue, Pskem-specific elevation-zoned inventory)
# and the GLIMS per-submission provenance record.
# Data: PUBLISHED/data/hydroclimate/glaciers-headwaters.geojson,
#       PUBLISHED/data/hydroclimate/glacier-source-attribution.csv,
#       PUBLISHED/data/hydroclimate/regional-glaciers.csv,
#       PUBLISHED/data/hydroclimate/pskem-glaciers.csv
# Paper-02 reference: Section 2.2.2.
#
# Run: Rscript ANALYSIS_R/remote/05_glacier_inventories.R

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

headwater_glims <- read_geojson_properties(data_path("hydroclimate", "glaciers-headwaters.geojson")) %>%
  mutate(across(c(area_km2, area_in_headwater_km2, elevation_min_m, elevation_max_m), as.numeric))
source_attribution <- read_csv(data_path("hydroclimate", "glacier-source-attribution.csv"), show_col_types = FALSE)
regional_pts <- read_csv(data_path("hydroclimate", "regional-glaciers.csv"), show_col_types = FALSE)
pskem_glac <- read_csv(data_path("hydroclimate", "pskem-glaciers.csv"), show_col_types = FALSE)

qc_summary(headwater_glims, "GLIMS-derived headwater glacier outlines")
check_count(nrow(headwater_glims), 25294, "total headwater glaciers")

header("Glacier count and area by headwater system")
by_system <- headwater_glims %>%
  group_by(system_id) %>%
  summarise(n_glaciers = n(), total_area_km2 = round(sum(area_km2, na.rm = TRUE), 1), .groups = "drop")
print(as.data.frame(by_system))
cat("Paper-02 states 20,750 (Amu Darya, 12,412.5 km2) and 4,544 (Syr Darya, 1,915.6 km2).\n")

cat(sprintf("\nTotal outlined area: %.1f km2; area within headwater formation: %.1f km2\n",
            sum(headwater_glims$area_km2, na.rm = TRUE),
            sum(headwater_glims$area_in_headwater_km2, na.rm = TRUE)))

header("Geographic extent (parsed from glacier_id, e.g. G067620E34655N)")
coords <- headwater_glims %>%
  mutate(m = regmatches(glacier_id, regexpr("G[0-9]{6}E[0-9]{5}N", glacier_id))) %>%
  filter(nchar(m) > 0) %>%
  mutate(lon = as.numeric(substr(m, 2, 7)) / 1000,
         lat = as.numeric(substr(m, 9, 13)) / 1000)
cat(sprintf("Longitude range: %.2f - %.2f E\n", min(coords$lon), max(coords$lon)))
cat(sprintf("Latitude range:  %.2f - %.2f N\n", min(coords$lat), max(coords$lat)))
cat("Paper-02 states 67.6-78.4 E, 34.6-42.5 N (Pamir through Tian Shan).\n")

header("Survey-date distribution (top 10 years)")
survey_years <- table(substr(headwater_glims$survey_date, 1, 4))
print(head(sort(survey_years, decreasing = TRUE), 10))
n_2002 <- sum(substr(headwater_glims$survey_date, 1, 4) == "2002", na.rm = TRUE)
cat(sprintf("\n%d of %d glaciers (%.0f%%) surveyed in 2002 (paper-02 states 16,764, 66%%).\n",
            n_2002, nrow(headwater_glims), 100 * n_2002 / nrow(headwater_glims)))

qc_summary(source_attribution, "GLIMS per-submission provenance (regional centres/analysts)")
check_count(nrow(source_attribution), 93, "GLIMS submission records")

header("Contributing institutions (chief_affiliation)")
aff <- source_attribution %>% count(chief_affiliation, sort = TRUE)
print(as.data.frame(aff))
cat("Paper-02 states Russian Academy of Sciences dominates (61/93), followed by\n",
    "Texas A and M University (12), Geographical Institute (10), University of\n",
    "Colorado (3), and single-digit contributions from four other institutions.\n")

header("Geographic area codes (GLIMS regional-centre labels)")
print(as.data.frame(source_attribution %>% count(geographic_area, sort = TRUE)))
cat("\nNone of these region labels names a dedicated modern Kyrgyz or Tajik national\n",
    "glacier agency; Central Asian coverage here comes through GLIMS's international\n",
    "regional-centre structure, chiefly the Russian Academy of Sciences submission.\n")

qc_summary(regional_pts, "Regional glacier point-centre catalogue (Kashkadarya/Surkhandarya)")
check_count(nrow(regional_pts), 210, "digitised glacier centres")
header("Basin split")
print(table(regional_pts$basin))
cat("Paper-02 states 60 Kashkadarya, 150 Surkhandarya, after removing one exact duplicate.\n")

qc_summary(pskem_glac, "Pskem-specific glacier inventory (GLIMS, catchment-scoped)", save_csv = FALSE)
cat(sprintf("\nElevation range across catalogued glaciers: %.0f - %.0f m\n",
            min(pskem_glac$elevation_min_m, na.rm = TRUE),
            max(pskem_glac$elevation_max_m, na.rm = TRUE)))
cat("This is a *third*, catchment-specific record, distinct from both the headwater\n",
    "outline set and the regional point-centre catalogue above; paper-02 SS2.2.2\n",
    "explicitly warns against treating any of the three as interchangeable.\n")
