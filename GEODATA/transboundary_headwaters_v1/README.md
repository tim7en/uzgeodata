# Transboundary headwater pilot v1

This package replaces national-boundary selection with upstream network
selection for the first hydroclimate pilot.

- `hydroatlas-level07-headwaters.geojson` contains complete HydroATLAS level-7
  units downloaded from `WWF/HydroATLAS/v1/Basins/level07` in Earth Engine.
- `manifest.json` records the asset, retrieval time, control units, counts,
  areas, checksum and quality notes.
- Web-ready geometries, routing and membership tables are published under
  `PUBLISHED/data/hydroclimate/`.

The two operational pilot definitions are all units routing to the configured
level-7 control unit immediately below the Panj-Vakhsh and Naryn-Karadarya
confluences. They are reproducible analytical boundaries, not a claim that the
points already equal an official hydrometric-station definition. Rebuild them
with:

```bash
npm run headwaters:basins
```

`SUB_AREA` is the source polygon-area attribute. Its sum can differ slightly
from the outlet's `UP_AREA`, which is a source upstream-accounting attribute;
both are preserved in the manifest instead of forcing them to agree.
