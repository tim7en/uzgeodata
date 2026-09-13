"""Layer 4: fitting something to the record, and reporting how badly it does.

A model is the first place in this stack where the output is not a measurement at
all. Everything below it can be checked against the thing it describes; a model
produces a number for a month nobody observed, and the only honest question is how
wrong it was on months it was not allowed to see.

So the harness is built around the refusals rather than around the fitting, which is
a dozen lines of linear algebra:

Skill is never reported on the data the model was fitted to. A fit evaluated on its
own training period reports how flexible it is, not how well it predicts, and the
number always looks good. There is no argument for it and no option to ask for it.

Skill is always relative to doing nothing. Alongside Nash-Sutcliffe the harness
reports the same ratio against the training period's calendar-month means -- the
forecast a reader could make with no model at all -- and for a strongly seasonal
target that is much the harder test. A model can post a fine efficiency purely by
reproducing the seasonal cycle, so a number against the mean without a number against
the climatology is how a useless model gets published.

Too little data means no answer. A handful of held-out months produces a skill score
with an enormous confidence interval and no confidence interval is printed, so the
threshold is enforced here instead.

What this is not: it is not calibrated hydrology. A linear model on monthly basin
means has no routing, no storage, no snowmelt physics and no groundwater. Where it
works it is a statistical association, and the summary says so rather than leaving a
reader to assume otherwise.
"""
from __future__ import annotations
import statistics

from . import query, variables

# Below this many held-out months the score is noise. Twenty-four is two annual
# cycles, which is the least that can distinguish skill from having learned the
# seasonality of the training period.
MINIMUM_EVALUATION = 24


class NotEnoughEvidence(ValueError):
    """A fit or a score the record cannot support."""


def predictors(store, basins, concepts, start=None, end=None, connection=None,
               weights=None):
    """A design matrix for a catchment: one row per month, one column per concept.

    `basins` is every basin the predictors should describe. For a single basin that is
    a list of one; for anything gauged at an outlet it is the whole upstream set,
    because a gauge integrates the area draining through it and the outlet polygon
    alone is a few square kilometres of a catchment that is hundreds. `weights` gives
    each basin's area, and the monthly value is the area-weighted mean -- an unweighted
    mean would let a small headwater polygon count as much as one twenty times its
    size.

    A month is kept only where every basin and every concept reported. Missing area is
    not filled: a catchment mean computed over the two thirds of the area that happened
    to report is not a catchment mean, and nothing downstream could tell the difference.
    The count of dropped months is returned so the loss is visible.
    """
    basins = list(basins)
    weights = weights or {basin: 1.0 for basin in basins}
    if set(weights) < set(basins):
        raise NotEnoughEvidence(
            f"no weight for {sorted(set(basins) - set(weights))}; an unweighted basin "
            "would silently drop out of the catchment mean")

    cells = {}
    for concept in concepts:
        attribute = variables.attribute(concept)
        for basin_id, _, month_start, value, *_ in query.observations(
                store, basins=basins, variables=[attribute], start=start, end=end,
                connection=connection):
            cells.setdefault((month_start.year, month_start.month), {})[
                (concept, str(basin_id))] = value

    total = sum(weights[basin] for basin in basins)
    months, matrix, dropped = [], [], 0
    for key in sorted(cells):
        entry, row, whole = cells[key], [], True
        for concept in concepts:
            values = [(weights[basin], entry.get((concept, str(basin)))) for basin in basins]
            if any(value is None for _, value in values):
                whole = False
                break
            row.append(sum(weight * value for weight, value in values) / total)
        if not whole:
            dropped += 1
            continue
        months.append(key)
        matrix.append(row)
    return {"months": months, "matrix": matrix, "concepts": list(concepts),
            "basins": basins, "dropped_months": dropped,
            "support": "area-weighted mean over the basins given, local support only"}


def _solve(design, target):
    """Ordinary least squares with an intercept, by normal equations."""
    import numpy

    matrix = numpy.column_stack([numpy.ones(len(design)), numpy.asarray(design, dtype=float)])
    coefficients, *_ = numpy.linalg.lstsq(matrix, numpy.asarray(target, dtype=float), rcond=None)
    return coefficients


def _apply(coefficients, design):
    import numpy

    matrix = numpy.column_stack([numpy.ones(len(design)), numpy.asarray(design, dtype=float)])
    return (matrix @ coefficients).tolist()


def skill(observed, predicted, reference=None):
    """How well the predictions did, against doing nothing.

    `reference` is what the model has to beat, one value per evaluation month: the
    expectation a reader could form with no model at all. Nash-Sutcliffe is reported
    against the evaluation period's own mean, which is the conventional definition;
    where a reference is supplied, the same ratio against it is reported too, and that
    is the harder and more honest test.
    """
    if len(observed) != len(predicted):
        raise NotEnoughEvidence("observations and predictions must align")
    errors = [prediction - actual for prediction, actual in zip(predicted, observed)]
    residual = sum(error ** 2 for error in errors)
    spread = sum((actual - statistics.fmean(observed)) ** 2 for actual in observed)

    scored = {
        "n": len(observed),
        "bias": statistics.fmean(errors),
        "mae": statistics.fmean([abs(error) for error in errors]),
        "rmse": (residual / len(observed)) ** 0.5,
        "nash_sutcliffe": 1 - residual / spread if spread > 0 else None,
        "reading": "Nash-Sutcliffe is zero when the model is no better than the mean of the "
                   "evaluation period and negative when it is worse. A high correlation "
                   "beside a negative efficiency means the model has learned the seasonal "
                   "cycle and nothing else.",
    }
    if reference is not None:
        if len(reference) != len(observed) or any(value is None for value in reference):
            raise NotEnoughEvidence("the reference must cover every evaluation month")
        against = sum((actual - value) ** 2 for actual, value in zip(observed, reference))
        scored["skill_against_climatology"] = (
            1 - residual / against if against > 0 else None)
    return scored


def fit(store, basins, target, concepts, train, evaluate, connection=None,
        weights=None, label=None):
    """Fit on one period, score on another, and never the same one.

    `target` is the observable being predicted: a mapping of (year, month) to value,
    supplied by the caller because the thing worth predicting is usually not in this
    store. `train` and `evaluate` are (start, end) month strings, and they must not
    overlap -- that is checked rather than trusted.
    """
    train_start, train_end = train
    evaluate_start, evaluate_end = evaluate
    if not all(isinstance(bound, str) for bound in (train_start, train_end,
                                                    evaluate_start, evaluate_end)):
        raise NotEnoughEvidence(
            "both periods must be stated as explicit YYYY-MM bounds; an open-ended "
            "period cannot be checked for overlap with the other")
    if not (train_end < evaluate_start or evaluate_end < train_start):
        raise NotEnoughEvidence(
            f"the training period {train} overlaps the evaluation period {evaluate}; "
            "a score on months the fit has seen is not a score")

    own = connection is None
    connection = connection or query.connect(store)
    try:
        fitting = predictors(store, basins, concepts, train_start, train_end,
                             connection, weights)
        testing = predictors(store, basins, concepts, evaluate_start, evaluate_end,
                             connection, weights)
    finally:
        if own:
            connection.close()

    def paired(block):
        months, design, actual = [], [], []
        for key, values in zip(block["months"], block["matrix"]):
            if key in target and target[key] is not None:
                months.append(key)
                design.append(values)
                actual.append(target[key])
        return months, design, actual

    train_months, train_design, train_actual = paired(fitting)
    test_months, test_design, test_actual = paired(testing)

    if len(train_actual) < len(concepts) + 2:
        raise NotEnoughEvidence(
            f"{len(train_actual)} training months for {len(concepts)} predictors; "
            "a fit with as many parameters as observations describes nothing")
    if len(test_actual) < MINIMUM_EVALUATION:
        raise NotEnoughEvidence(
            f"{len(test_actual)} months held out, fewer than the {MINIMUM_EVALUATION} "
            "needed to tell skill from having learned the seasonal cycle")

    coefficients = _solve(train_design, train_actual)
    predicted = _apply(coefficients, test_design)

    # The reference the model must beat: the training period's mean for each calendar
    # month, which is the forecast a reader could make with no model at all.
    seasonal = {}
    for (year, month), value in zip(train_months, train_actual):
        seasonal.setdefault(month, []).append(value)
    climatology = {month: statistics.fmean(values) for month, values in seasonal.items()}
    baseline = [climatology.get(month) for _, month in test_months]

    if any(value is None for value in baseline):
        raise NotEnoughEvidence(
            "the evaluation period contains a calendar month the training period never "
            "saw, so there is no reference to score the model against")
    scored = skill(test_actual, predicted, baseline)

    return {
        "target": label, "basins": list(basins), "concepts": list(concepts),
        "train": {"period": train, "months": len(train_actual),
                  "dropped_for_missing_predictors": fitting["dropped_months"]},
        "evaluate": {"period": evaluate, "months": len(test_actual),
                     "dropped_for_missing_predictors": testing["dropped_months"]},
        "coefficients": dict(zip(["intercept"] + list(concepts), coefficients.tolist())),
        "skill": scored,
        "meaning": "A linear association between monthly basin means, evaluated on months the "
                   "fit did not see. It contains no routing, storage, snowmelt physics or "
                   "groundwater, so it predicts without explaining and should not be read as "
                   "a calibrated hydrological model.",
    }
