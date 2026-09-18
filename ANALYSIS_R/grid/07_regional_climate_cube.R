# Grid data: the TerraClimate/ERA5-Land/MODIS monthly cube reduced onto
# level-12 HydroBASINS units (the record paper-01's trend study consumes).
# Data: PUBLISHED/data/atlas/cube/ (Hive-partitioned Parquet, one partition
#       per variable=<attribute_id>)
# Paper-02 reference: Section 2.3.
#
# Requires the 'arrow' package: install.packages("arrow", type = "binary")
#
# Run: Rscript ANALYSIS_R/grid/07_regional_climate_cube.R

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

if (!requireNamespace("arrow", quietly = TRUE)) {
  stop("The 'arrow' package is required to read the Parquet cube. Install with:\n",
       '  install.packages("arrow", type = "binary")')
}
suppressPackageStartupMessages(library(arrow))

cube_dir <- data_path("atlas", "cube")
parquet_files <- list.files(cube_dir, pattern = "\\.parquet$", recursive = TRUE, full.names = TRUE)
cat(sprintf("Found %d Parquet partitions under %s\n", length(parquet_files), cube_dir))

ds <- open_dataset(parquet_files, partitioning = "hive")

header(paste0("Regional climate cube -- ", format(nrow(ds), big.mark = ","), " rows"))
print(ds$schema)

header("Cross-checks against paper-02 SS2.3")
n_basins <- ds %>% summarise(n = n_distinct(basin_id)) %>% collect() %>% pull(n)
check_count(n_basins, 7445, "distinct basins in the cube")

n_vars <- ds %>% summarise(n = n_distinct(attribute_id)) %>% collect() %>% pull(n)
cat(sprintf("Distinct variable partitions (attribute_id): %d\n", n_vars))

yr_range <- ds %>% summarise(min_y = min(year), max_y = max(year)) %>% collect()
check_count(yr_range$min_y, 2003, "first year in the cube")
check_count(yr_range$max_y, 2024, "last year in the cube")

header("Row count, missing-value share and range by variable")
per_var <- ds %>%
  group_by(attribute_id) %>%
  summarise(
    n_rows = n(),
    n_basins = n_distinct(basin_id),
    n_na = sum(as.integer(is.na(value))),
    min_value = min(value, na.rm = TRUE),
    max_value = max(value, na.rm = TRUE)
  ) %>%
  collect() %>%
  arrange(attribute_id)
print(as.data.frame(per_var), row.names = FALSE)
readr::write_csv(per_var, out_path("regional_climate_cube_per_variable_qc.csv"))

cat("\n'run' (ERA5-Land runoff) and 'tmp' (ERA5-Land mean temperature) are the two\n",
    "variables paper-01/paper-02 state are withheld from the level-12 trend study\n",
    "on resolution grounds (~1.05 native ERA5-Land cells per median basin); note\n",
    "they are still *present* here as raw basin-mean values -- the withholding is\n",
    "a downstream analysis decision, not a gap in this record.\n")
