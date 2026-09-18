# Grid data: SRTM-derived elevation-band terrain stratification for the
# headwater formation zones (used to stratify the ERA5-Land headwater series).
# Data: PUBLISHED/data/hydroclimate/headwater-elevation-bands.csv (+ manifest)
# Paper-02 reference: Section 2.3 (grid-record File manifest).
#
# Run: Rscript ANALYSIS_R/grid/08_headwater_elevation_bands.R

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

bands <- read_csv(data_path("hydroclimate", "headwater-elevation-bands.csv"), show_col_types = FALSE)
manifest <- fromJSON(data_path("hydroclimate", "headwater-elevation-bands.manifest.json"))

qc_summary(bands, "Headwater elevation bands")

header("Band definitions vs. manifest")
print(bands %>% select(system_id, river_system_id, elevation_band, minimum_m_inclusive,
                        maximum_m_exclusive, area_km2, share_percent))
cat("\nManifest band IDs:\n")
print(manifest$bands$id)

header("Area-share consistency check (should sum close to 100% per system/river_system)")
share_check <- bands %>%
  group_by(system_id, river_system_id) %>%
  summarise(total_share = sum(share_percent, na.rm = TRUE), .groups = "drop")
print(as.data.frame(share_check))
cat("\nA total far from 100% would indicate a band boundary or area-weighting bug;\n",
    "this script only flags the number, it does not diagnose or fix it.\n")

cat(sprintf("\nSource: %s at %s m native resolution, reduced at %s m (manifest).\n",
            manifest$source$asset, manifest$source$nativeResolutionMetres,
            manifest$source$analysisScaleMetres))
