# Shared helpers for the UzGeoData per-dataset QC scripts (ANALYSIS_R/).
#
# Each script under site/, remote/, grid/ and modelled/ sources this file,
# reads one dataset from PUBLISHED/data/, and reports what is actually in it:
# dimensions, missingness, duplicates, ranges, and (where paper-02 states a
# count) a PASS/MISMATCH check against that stated count. Nothing here fits a
# model or recomputes a scientific result -- it audits the released files.

suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(jsonlite)
})

# Locate the repository root by walking up from a starting directory until a
# known root file is found. The caller (each dataset script) has already
# worked out its own directory correctly -- via ANALYSIS_R/site/01_*.R's
# `.script_dir`, which handles both `Rscript foo.R` and being source()d from
# run_all.R -- and passes it in as `start`. commandArgs() cannot be trusted
# here: when this file is sourced from inside a sourced dataset script (the
# run_all.R case), it still reports run_all.R's own path, not the caller's.
find_repo_root <- function(start = getwd()) {
  dir <- start
  for (i in 1:8) {
    if (file.exists(file.path(dir, "DATA-LICENSING.md"))) return(dir)
    parent <- dirname(dir)
    if (identical(parent, dir)) break
    dir <- parent
  }
  stop("Could not locate the repository root above ", start,
       " (looked for DATA-LICENSING.md).")
}

ROOT <- find_repo_root(start = if (exists(".script_dir", inherits = FALSE)) .script_dir else getwd())
data_path <- function(...) file.path(ROOT, "PUBLISHED", "data", ...)

out_path <- function(...) {
  d <- file.path(ROOT, "ANALYSIS_R", "output")
  if (!dir.exists(d)) dir.create(d, recursive = TRUE)
  file.path(d, ...)
}

# GeoJSON point/polygon layers in this release carry the interesting data in
# feature properties, not geometry. This project has no sf/geojsonsf
# dependency installed, and a descriptive QC pass over a station or point
# layer only needs the properties table, so this reads properties with
# jsonlite rather than pulling in a spatial stack.
read_geojson_properties <- function(path) {
  gj <- fromJSON(path, simplifyVector = FALSE)
  props <- lapply(gj$features, function(f) f$properties)
  bind_rows(lapply(props, function(p) {
    # Every value is coerced to character here: GeoJSON properties are not
    # guaranteed to parse to the same R type on every feature (a numeric
    # field can arrive as integer on one feature and double, or NA, on
    # another), and a per-dataset script casts the columns it needs back to
    # numeric/date explicitly. This trades convenience for not silently
    # dropping rows when bind_rows() would otherwise hit a type conflict.
    flat <- lapply(p, function(x) {
      if (is.null(x) || length(x) == 0) return(NA_character_)
      # A property holding a JSON array (e.g. a station's list of measured
      # variables) is collapsed to a single comma-separated string rather
      # than dropped or exploded into extra rows.
      if (length(x) > 1 || is.list(x)) return(paste(unlist(x), collapse = ", "))
      as.character(x)
    })
    as.data.frame(flat, stringsAsFactors = FALSE)
  }))
}

header <- function(title) {
  cat("\n", strrep("=", nchar(title) + 4), "\n", sep = "")
  cat("= ", title, " =\n", sep = "")
  cat(strrep("=", nchar(title) + 4), "\n", sep = "")
}

# One row per column: type, missingness, distinct count, and a numeric range
# where the column has one. This is the descriptive QC summary every script
# in ANALYSIS_R/ produces before any dataset-specific checks.
qc_summary <- function(df, name, save_csv = TRUE) {
  header(paste0(name, " -- ", nrow(df), " rows x ", ncol(df), " columns"))

  dup_rows <- sum(duplicated(df))
  cat("Duplicate rows:", dup_rows, "\n\n")

  summary_tbl <- bind_rows(lapply(names(df), function(col) {
    x <- df[[col]]
    n_na <- sum(is.na(x))
    is_num <- is.numeric(x)
    data.frame(
      column = col,
      type = class(x)[1],
      n = length(x),
      n_missing = n_na,
      pct_missing = round(100 * n_na / length(x), 2),
      n_distinct = dplyr::n_distinct(x, na.rm = TRUE),
      min = if (is_num && any(!is.na(x))) suppressWarnings(min(x, na.rm = TRUE)) else NA_real_,
      max = if (is_num && any(!is.na(x))) suppressWarnings(max(x, na.rm = TRUE)) else NA_real_,
      stringsAsFactors = FALSE
    )
  }))

  print(summary_tbl, row.names = FALSE)

  if (save_csv) {
    out_file <- out_path(paste0(gsub("[^A-Za-z0-9]+", "_", tolower(name)), "_qc.csv"))
    readr::write_csv(summary_tbl, out_file)
    cat("\nSummary written to:", out_file, "\n")
  }

  invisible(summary_tbl)
}

# Compares an actual count in the released file against the count paper-02
# states for it, and prints PASS/MISMATCH rather than assuming agreement.
check_count <- function(actual, expected, label) {
  status <- if (actual == expected) "PASS" else "MISMATCH"
  cat(sprintf("[%s] %s: file has %s, paper-02 states %s\n",
              status, label, format(actual, big.mark = ","), format(expected, big.mark = ",")))
  invisible(actual == expected)
}

# Nash-Sutcliffe efficiency, used by the modelled-data scripts to
# independently recompute a skill score already reported in a manifest or
# case-study document, rather than trusting the reported figure blind.
nse <- function(observed, simulated) {
  ok <- is.finite(observed) & is.finite(simulated)
  observed <- observed[ok]; simulated <- simulated[ok]
  1 - sum((observed - simulated)^2) / sum((observed - mean(observed))^2)
}
