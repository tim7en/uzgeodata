# Amu Darya and Syr Darya transboundary natural systems v2

This package keeps two spatial scopes and three resolutions:

- `full_basin`: all HydroATLAS units sharing `MAIN_BAS` with the river-system
  control unit;
- `headwater_formation`: the nested subset whose `NEXT_DOWN` route reaches the
  upper control unit;
- levels 7, 10 and 12: coarse climate, operational hydrology and detailed
  reference frames respectively.

The exact Earth Engine GeoJSON downloads are named
`hydroatlas-levelNN-full-basins.geojson`. Web-simplified copies, routing CSVs,
scope membership and the cross-level Pfafstetter hierarchy are under
`PUBLISHED/data/hydroclimate/`.

Level 12 uses the same standard `HYBAS_ID`, `NEXT_DOWN`, `MAIN_BAS` and
`PFAF_ID` fields as the existing downstream BasinATLAS reference. This makes a
join possible; it does not make natural drainage equivalent to managed canals,
reservoir operations or water allocation.

`full_basin` means the complete natural main-basin system represented by the
HydroATLAS routing model. Official interstate or water-management basin areas
can differ and must be maintained as a separately sourced managed geography.
