# Remote observations: infrastructure inventories joined to HydroBASINS
# routing geometry (dams, water bodies/reservoirs).
# Data: PUBLISHED/data/hydroclimate/dams-transboundary.csv,
#       PUBLISHED/data/hydroclimate/water-bodies-transboundary.csv
# Paper-02 reference: Section 2.2.3.
#
# Run: Rscript ANALYSIS_R/remote/06_infrastructure_inventories.R

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

dams <- read_csv(data_path("hydroclimate", "dams-transboundary.csv"), show_col_types = FALSE)
water_bodies <- read_csv(data_path("hydroclimate", "water-bodies-transboundary.csv"), show_col_types = FALSE)

qc_summary(dams, "Dams (Global Dam Watch v1.0, joined to HydroBASINS)")
check_count(nrow(dams), 100, "dams native to a level-12 unit of the domain")
check_count(sum(!is.na(dams$grand_id)), 24, "dams with a named/GRanD-linked ID")

header("Main-use breakdown")
print(table(dams$main_use, useNA = "ifany"))

qc_summary(water_bodies, "Water bodies (HydroLAKES v1.0, joined to HydroBASINS)")
check_count(nrow(water_bodies), 1393, "water bodies")
check_count(sum(water_bodies$water_body_type == "reservoir", na.rm = TRUE), 23, "reservoirs")
check_count(sum(water_bodies$water_body_type == "lake", na.rm = TRUE), 1370, "lakes")

reservoir_storage <- sum(water_bodies$storage_volume_mcm[water_bodies$water_body_type == "reservoir"],
                          na.rm = TRUE)
cat(sprintf("\nSummed reservoir storage_volume_mcm: %s (paper-02 states 50,241.3 Mcm)\n",
            format(round(reservoir_storage, 1), big.mark = ",")))

header("Water-body-type breakdown")
print(table(water_bodies$water_body_type, useNA = "ifany"))

cat("\nThese are catalogue-to-geometry joins, not field-verified operating records;\n",
    "reservoir storage above is nameplate capacity from the source catalogue, not\n",
    "an observed water level.\n")
