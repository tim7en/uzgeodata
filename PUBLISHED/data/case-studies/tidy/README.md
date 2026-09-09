# Chirchik / Pskem case study - tidy tables

Flat CSV, one row per observation. Missing values are empty, not `nan`. Numbers
are rounded to what the measurement supports. Column meanings, including units,
are in `data_dictionary.csv`.

R:

    daily <- read.csv("pskem_daily.csv")
    scores <- read.csv("model_scores.csv")
    subset(scores, evaluation == "chronological" & metric == "nse")

Python:

    import pandas as pd
    daily = pd.read_csv("pskem_daily.csv", parse_dates=["date"])

The two evaluations are different experiments on the same model structure and
are not directly comparable: `stratified` places wet and dry years on both sides
of the split, `chronological` scores only years that follow every calibration
year. Filter on `evaluation` before comparing anything.

Provenance, input hashes and the commands that produce these tables are in
`../reproducibility-package.json`.
