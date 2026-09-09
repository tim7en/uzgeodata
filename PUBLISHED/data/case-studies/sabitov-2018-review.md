# Sabitov’s Pskem hydrologic modelling: results review

T. Y. Sabitov’s 2018 SUNY ESF master’s thesis compares four increasingly complex models for Pskem water years 2013–2015. The abstract and Table 2-4 report:

| Model | Approach | Monthly R², abstract | Daily NSE, Table 2-4 | Monthly NSE, Table 2-4 |
| --- | --- | ---: | ---: | ---: |
| 1 | Simplified balance | 0.84 | 0.70 | 0.90 |
| 2 | Spatial adjustment and ET | 0.77 | 0.23 | 0.24 |
| 3 | Multilevel SCS curve number | 0.93 | 0.76 | 0.77 |
| 4 | Spatially adjusted multilevel SCS | 0.85 | 0.29 | 0.69 |

Model 1 leads monthly NSE but its best fit uses zero evapotranspiration. Model 3 leads daily NSE and is favoured in the discussion. Thus neither complexity nor one score alone establishes physical credibility. The abstract uses R² while some result passages use correlation terminology; these should not be silently equated. Reported glacier contributions remain model estimates. [Source: author-uploaded thesis, abstract, pp. 46–54, especially Table 2-4 on p. 53](https://www.researchgate.net/publication/325033449_HYDROLOGIC_MODELING_OF_GLACIATED_WATERSHED_IN_CENTRAL_ASIA).

## Implications for the current case study

Our monthly experiment uses a different boundary approximation and a 2011–2017 holdout: forest NSE 0.794, seasonal baseline 0.747, bucket 0.582 and Bayesian linear 0.665. These cannot rank our implementation against the thesis. We have not reproduced its four models or established an identical calibration/evaluation split.

The next useful experiment is a daily SCS model with separate snow and glacier stores. Curve numbers need hydrologic soil groups and antecedent moisture assumptions alongside the new Esri land cover; 10 m land-cover classes alone cannot determine them. Calibrate on earlier years, freeze parameters, and reserve later discharge and satellite snow for independent checks. Keep ET constrained instead of improving a fit by removing that water loss. Resolve the gauge boundary before claiming transferable parameters.

The full institutional PDF download was inaccessible during this review; the results above were checked against the publicly indexed author-uploaded text. Resolve notation and transcription differences against the original figures before numerical replication. Original source records and our existing model scores have not been changed.
