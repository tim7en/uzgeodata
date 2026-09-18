# Modelled data: Pskem daily HBV-type hydrological model, both published
# evaluation splits.
# Data: PUBLISHED/data/case-studies/pskem-daily-model.{csv,json},
#       PUBLISHED/data/case-studies/model-audit/chronological-20260909/pskem-daily-model.csv,
#       PUBLISHED/data/case-studies/model-review.json
# Paper-02 reference: Section 2.4.1.
#
# Run: Rscript ANALYSIS_R/modelled/09_pskem_hbv_model.R

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

reference <- read_csv(data_path("case-studies", "pskem-daily-model.csv"), show_col_types = FALSE)
chronological <- read_csv(
  data_path("case-studies", "model-audit", "chronological-20260909", "pskem-daily-model.csv"),
  show_col_types = FALSE)
review <- fromJSON(data_path("case-studies", "model-review.json"))

qc_summary(reference, "Pskem HBV model -- reference (stratified) run")
qc_summary(chronological, "Pskem HBV model -- chronological-holdout run", save_csv = FALSE)

header("Period breakdown (reference run)")
print(table(reference$period, useNA = "ifany"))
header("Period breakdown (chronological run)")
print(table(chronological$period, useNA = "ifany"))

recompute_nse <- function(df, label) {
  df_test <- df %>% filter(!is.na(observed_mm), !is.na(simulated_mm))
  score <- nse(df_test$observed_mm, df_test$simulated_mm)
  cat(sprintf("  %-16s n = %5d, recomputed NSE (all non-NA rows) = %.4f\n",
              label, nrow(df_test), score))
  invisible(score)
}

header("Independently recomputed NSE (all rows, not split by period)")
recompute_nse(reference, "reference:")
recompute_nse(chronological, "chronological:")
cat("Paper-02 reports NSE by test-period split (daily/monthly/seasonal), not over\n",
    "the whole file, so this whole-file NSE is expected to differ from the\n",
    "headline daily-test numbers below; it is a sanity check on model fit, not a\n",
    "reproduction of the reported score.\n")

header("Published skill by split (from model-review.json)")
splits <- c("candidate", "reference")
for (s in splits) {
  sk <- review[[s]]
  split_label <- if (is.null(sk$split)) "see manifest" else sk$split
  cat(sprintf("\n%s (%s split):\n", s, split_label))
  for (window in c("daily", "monthly", "seasonal")) {
    w <- sk[[window]]
    if (!is.null(w)) cat(sprintf("  %-9s n=%4d  NSE=%7.4f  KGE=%7.4f  RMSE(mm)=%.4f\n",
                                  window, w$n, w$nse, w$kge, w$rmseMm))
  }
}
cat(sprintf("\nProject decision (model-review.json): \"%s\"\n", review$decision))
