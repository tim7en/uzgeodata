# BasinATLAS attribute function library

Draft source-based pseudocode. All 281 attribute functions are specified. Only ele_mt_sav has a pilot implementation; none is claimed independently reproduced. Shared support, validation and storage rules are in [METHODOLOGY.md](METHODOLOGY.md).

## C06 ? aet

Source: Global High-Resolution Soil-Water Balance; Trabucco & Zomer 2010. [Catalogue page 20](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=20).

Units: millimeters. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_aet(source_lock)`:

Load Global High-Resolution Soil-Water Balance AET surfaces; select monthly or annual water-balance output then spatial mean; retain the original WorldClim/Global-PET forcing and soil-water assumptions.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
aet_mm_s01(basin, source_lock):
    field = prepare_aet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='01')
    return encode_and_validate(value, catalogue='C06', run_manifest=True)
```

```text
aet_mm_s02(basin, source_lock):
    field = prepare_aet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='02')
    return encode_and_validate(value, catalogue='C06', run_manifest=True)
```

```text
aet_mm_s03(basin, source_lock):
    field = prepare_aet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='03')
    return encode_and_validate(value, catalogue='C06', run_manifest=True)
```

```text
aet_mm_s04(basin, source_lock):
    field = prepare_aet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='04')
    return encode_and_validate(value, catalogue='C06', run_manifest=True)
```

```text
aet_mm_s05(basin, source_lock):
    field = prepare_aet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='05')
    return encode_and_validate(value, catalogue='C06', run_manifest=True)
```

```text
aet_mm_s06(basin, source_lock):
    field = prepare_aet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='06')
    return encode_and_validate(value, catalogue='C06', run_manifest=True)
```

```text
aet_mm_s07(basin, source_lock):
    field = prepare_aet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='07')
    return encode_and_validate(value, catalogue='C06', run_manifest=True)
```

```text
aet_mm_s08(basin, source_lock):
    field = prepare_aet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='08')
    return encode_and_validate(value, catalogue='C06', run_manifest=True)
```

```text
aet_mm_s09(basin, source_lock):
    field = prepare_aet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='09')
    return encode_and_validate(value, catalogue='C06', run_manifest=True)
```

```text
aet_mm_s10(basin, source_lock):
    field = prepare_aet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='10')
    return encode_and_validate(value, catalogue='C06', run_manifest=True)
```

```text
aet_mm_s11(basin, source_lock):
    field = prepare_aet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='11')
    return encode_and_validate(value, catalogue='C06', run_manifest=True)
```

```text
aet_mm_s12(basin, source_lock):
    field = prepare_aet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='12')
    return encode_and_validate(value, catalogue='C06', run_manifest=True)
```

```text
aet_mm_syr(basin, source_lock):
    field = prepare_aet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='yr')
    return encode_and_validate(value, catalogue='C06', run_manifest=True)
```

```text
aet_mm_uyr(basin, source_lock):
    field = prepare_aet(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='yr')
    return encode_and_validate(value, catalogue='C06', run_manifest=True)
```

## C07 ? ari

Source: Global Aridity Index v1; Zomer et al. 2008. [Catalogue page 21](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=21).

Units: index value (x100). Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_ari(source_lock)`:

Use Global-Aridity v1 or recreate per-cell annual precipitation/PET; handle zero PET explicitly; cap physical index at 100 per C07; spatial mean then encode x100. Ratio of basin means is a different calculation.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
ari_ix_sav(basin, source_lock):
    field = prepare_ari(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='C07', run_manifest=True)
```

```text
ari_ix_uav(basin, source_lock):
    field = prepare_ari(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='C07', run_manifest=True)
```

## C02 ? cls

Source: Global Environmental Stratification (GEnS); Metzger et al. 2013. [Catalogue page 16](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=16).

Units: classes (125). Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_cls(source_lock)`:

Load GEnS environmental strata (125 classes); select spatial majority under the original class grid; preserve legend IDs.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
cls_cl_smj(basin, source_lock):
    field = prepare_cls(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mj')
    return encode_and_validate(value, catalogue='C02', run_manifest=True)
```

## S01 ? cly

Source: SoilGrids1km; Hengl et al. 2014. [Catalogue page 41](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=41).

Units: percent. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_cly(source_lock)`:

Select SoilGrids1km clay fraction at 0-5 cm; spatial mean over valid support, retain percent units.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
cly_pc_sav(basin, source_lock):
    field = prepare_cly(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='S01', run_manifest=True)
```

```text
cly_pc_uav(basin, source_lock):
    field = prepare_cly(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='S01', run_manifest=True)
```

## C01 ? clz

Source: Global Environmental Stratification (GEnS); Metzger et al. 2013. [Catalogue page 15](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=15).

Units: classes (18). Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_clz(source_lock)`:

Load GEnS environmental zones (18 classes); select spatial majority under the original class grid; preserve legend IDs.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
clz_cl_smj(basin, source_lock):
    field = prepare_clz(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mj')
    return encode_and_validate(value, catalogue='C01', run_manifest=True)
```

## C08 ? cmi

Source: WorldClim v1.4 and Global-PET v1; Hijmans et al. 2005. [Catalogue page 22](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=22).

Units: index value (x100). Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_cmi(source_lock)`:

For each pixel and period calculate P/PET-1 if P<PET, else 1-PET/P; handle P=PET=0 explicitly; spatial mean then encode x100. Annual index uses annual inputs, not mean monthly indices.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
cmi_ix_s01(basin, source_lock):
    field = prepare_cmi(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='01')
    return encode_and_validate(value, catalogue='C08', run_manifest=True)
```

```text
cmi_ix_s02(basin, source_lock):
    field = prepare_cmi(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='02')
    return encode_and_validate(value, catalogue='C08', run_manifest=True)
```

```text
cmi_ix_s03(basin, source_lock):
    field = prepare_cmi(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='03')
    return encode_and_validate(value, catalogue='C08', run_manifest=True)
```

```text
cmi_ix_s04(basin, source_lock):
    field = prepare_cmi(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='04')
    return encode_and_validate(value, catalogue='C08', run_manifest=True)
```

```text
cmi_ix_s05(basin, source_lock):
    field = prepare_cmi(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='05')
    return encode_and_validate(value, catalogue='C08', run_manifest=True)
```

```text
cmi_ix_s06(basin, source_lock):
    field = prepare_cmi(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='06')
    return encode_and_validate(value, catalogue='C08', run_manifest=True)
```

```text
cmi_ix_s07(basin, source_lock):
    field = prepare_cmi(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='07')
    return encode_and_validate(value, catalogue='C08', run_manifest=True)
```

```text
cmi_ix_s08(basin, source_lock):
    field = prepare_cmi(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='08')
    return encode_and_validate(value, catalogue='C08', run_manifest=True)
```

```text
cmi_ix_s09(basin, source_lock):
    field = prepare_cmi(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='09')
    return encode_and_validate(value, catalogue='C08', run_manifest=True)
```

```text
cmi_ix_s10(basin, source_lock):
    field = prepare_cmi(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='10')
    return encode_and_validate(value, catalogue='C08', run_manifest=True)
```

```text
cmi_ix_s11(basin, source_lock):
    field = prepare_cmi(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='11')
    return encode_and_validate(value, catalogue='C08', run_manifest=True)
```

```text
cmi_ix_s12(basin, source_lock):
    field = prepare_cmi(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='12')
    return encode_and_validate(value, catalogue='C08', run_manifest=True)
```

```text
cmi_ix_syr(basin, source_lock):
    field = prepare_cmi(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='yr')
    return encode_and_validate(value, catalogue='C08', run_manifest=True)
```

```text
cmi_ix_uyr(basin, source_lock):
    field = prepare_cmi(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='yr')
    return encode_and_validate(value, catalogue='C08', run_manifest=True)
```

## L08 ? crp

Source: EarthStat; Ramankutty et al. 2008. [Catalogue page 31](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=31).

Units: percent cover. Reference period: circa 2000.

`prepare_crp(source_lock)`:

Read EarthStat circa-2000 cropland fractions; sum fraction*cell_area over support; divide by support area and multiply by 100.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
crp_pc_sse(basin, source_lock):
    field = prepare_crp(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='L08', run_manifest=True)
```

```text
crp_pc_use(basin, source_lock):
    field = prepare_crp(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='L08', run_manifest=True)
```

## H01 ? dis

Source: WaterGAP v2.2 (data of 2014); Döll et al. 2003. [Catalogue page 2](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=2).

Units: cubic meters/second. Reference period: 1971-2000.

`prepare_dis(source_lock)`:

Load WaterGAP 2.2 (2014) naturalized discharge for 1971-2000; reproduce the published 0.5-degree to 15-arc-second downscaling; select annual mean/minimum/maximum field; sample at the basin pour point. Do not substitute a basin mean or sum of discharge.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
dis_m3_pmn(basin, source_lock):
    field = prepare_dis(source_lock)
    support = resolve_support(basin, 'p', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mn')
    return encode_and_validate(value, catalogue='H01', run_manifest=True)
```

```text
dis_m3_pmx(basin, source_lock):
    field = prepare_dis(source_lock)
    support = resolve_support(basin, 'p', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mx')
    return encode_and_validate(value, catalogue='H01', run_manifest=True)
```

```text
dis_m3_pyr(basin, source_lock):
    field = prepare_dis(source_lock)
    support = resolve_support(basin, 'p', pinned_geometry)
    value = reduce_per_source(field, support, dimension='yr')
    return encode_and_validate(value, catalogue='H01', run_manifest=True)
```

## H07 ? dor

Source: HydroSHEDS and Global Reservoir and Dams (GRanD) database v1.1; Lehner et al. 2011. [Catalogue page 8](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=8).

Units: percent (x10). Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_dor(source_lock)`:

At the pour point compute 100 * upstream_reservoir_capacity_m3 / annual_natural_discharge_volume_m3; cap at 1000 percent per H07. Resolve original year-length convention; zero discharge requires an explicit missing/outlier rule.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
dor_pc_pva(basin, source_lock):
    field = prepare_dor(source_lock)
    support = resolve_support(basin, 'p', pinned_geometry)
    value = reduce_per_source(field, support, dimension='va')
    return encode_and_validate(value, catalogue='H07', run_manifest=True)
```

## P01 ? ele

Source: EarthEnv-DEM90; Robinson et al. 2014. [Catalogue page 12](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=12).

Units: meters a.s.l.. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_ele(source_lock)`:

Aggregate EarthEnv-DEM90 from 3 to 15 arc-seconds using mean first; then calculate requested basin mean, spatial minimum or spatial maximum; use weighted sufficient statistics for upstream mean.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
ele_mt_sav(basin, source_lock):
    field = prepare_ele(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='P01', run_manifest=True)
```

```text
ele_mt_smn(basin, source_lock):
    field = prepare_ele(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mn')
    return encode_and_validate(value, catalogue='P01', run_manifest=True)
```

```text
ele_mt_smx(basin, source_lock):
    field = prepare_ele(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mx')
    return encode_and_validate(value, catalogue='P01', run_manifest=True)
```

```text
ele_mt_uav(basin, source_lock):
    field = prepare_ele(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='P01', run_manifest=True)
```

## S08 ? ero

Source: RUSLE-based Global Soil Erosion Modelling platform (GloSEM) v1.2; Borrelli et al. 2017. [Catalogue page 48](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=48).

Units: kg/hectare per year. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_ero(source_lock)`:

Select the original GloSEM v1.2 RUSLE erosion-rate scenario; spatial mean and unit conversion to the atlas unit. Resolve selected scenario/year; excludes gully and tillage erosion.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
ero_kh_sav(basin, source_lock):
    field = prepare_ero(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='S08', run_manifest=True)
```

```text
ero_kh_uav(basin, source_lock):
    field = prepare_ero(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='S08', run_manifest=True)
```

## L17 ? fec

Source: Freshwater Ecoregions of the World (FEOW); Abell et al. 2008. [Catalogue page 40](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=40).

Units: classes (426). Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_fec(source_lock)`:

Read the HydroATLAS-adjusted FEOW map, including island IDs above 900; select majority freshwater ecoregion. Generic FEOW without atlas revisions is not exact reproduction.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
fec_cl_smj(basin, source_lock):
    field = prepare_fec(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mj')
    return encode_and_validate(value, catalogue='L17', run_manifest=True)
```

## L16 ? fmh

Source: Freshwater Ecoregions of the World (FEOW); Abell et al. 2008. [Catalogue page 39](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=39).

Units: classes (13). Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_fmh(source_lock)`:

Read HydroATLAS-adjusted FEOW habitat assignments; select majority major habitat type with pinned lookup.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
fmh_cl_smj(basin, source_lock):
    field = prepare_fmh(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mj')
    return encode_and_validate(value, catalogue='L16', run_manifest=True)
```

## L07 ? for

Source: GLC2000; Bartholomé & Belward 2005. [Catalogue page 30](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=30).

Units: percent cover. Reference period: 2000.

`prepare_for(source_lock)`:

Read GLC2000 and combine forest classes 1-8; calculate their combined area percentage in local or unique upstream support.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
for_pc_sse(basin, source_lock):
    field = prepare_for(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='L07', run_manifest=True)
```

```text
for_pc_use(basin, source_lock):
    field = prepare_for(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='L07', run_manifest=True)
```

## A07 ? gad

Source: Global Administrative Areas (GADM) v2.0; University of Berkeley 2012. [Catalogue page 55](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=55).

Units: ID number. Reference period: 2012.

`prepare_gad(source_lock)`:

Read GADM v2 2012 country IDs; choose majority over basin; preserve ID lookup. Result describes basin association, not political boundaries.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
gad_id_smj(basin, source_lock):
    field = prepare_gad(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mj')
    return encode_and_validate(value, catalogue='A07', run_manifest=True)
```

## A08 ? gdp

Source: Gross Domestic Product Purchasing Power Parity (GDP PPP) v2; Kummu et al. 2018. [Catalogue page 56](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=56).

Units: US dollars. Reference period: 2015.

`prepare_gdp(source_lock)`:

For av use 2015 GDP PPP per-capita grid and original spatial averaging; for su use 2015 GDP-total grid and conservative sum. Currency is 2011 international dollars; resolve native resolutions independently.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
gdp_ud_sav(basin, source_lock):
    field = prepare_gdp(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='A08', run_manifest=True)
```

```text
gdp_ud_ssu(basin, source_lock):
    field = prepare_gdp(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='su')
    return encode_and_validate(value, catalogue='A08', run_manifest=True)
```

```text
gdp_ud_usu(basin, source_lock):
    field = prepare_gdp(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='su')
    return encode_and_validate(value, catalogue='A08', run_manifest=True)
```

## L11 ? gla

Source: Global Land Ice Measurements from Space (GLIMS); GLIMS & NSIDC 2012. [Catalogue page 34](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=34).

Units: percent cover. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_gla(source_lock)`:

Read the pinned GLIMS inventory; select the original outline version per glacier, union overlaps and compute glacier area percentage. Preserve observation dates; do not treat mixed dates as one observation year.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
gla_pc_sse(basin, source_lock):
    field = prepare_gla(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='L11', run_manifest=True)
```

```text
gla_pc_use(basin, source_lock):
    field = prepare_gla(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='L11', run_manifest=True)
```

## L01 ? glc-cl

Source: GLC2000; Bartholomé & Belward 2005. [Catalogue page 24](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=24).

Units: classes (22). Reference period: 2000.

`prepare_glc_cl(source_lock)`:

Read GLC2000 22-class map; choose basin majority class using the pinned HydroATLAS legend and documented tie rule.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
glc_cl_smj(basin, source_lock):
    field = prepare_glc_cl(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mj')
    return encode_and_validate(value, catalogue='L01', run_manifest=True)
```

## L02 ? glc-pc

Source: GLC2000; Bartholomé & Belward 2005. [Catalogue page 25](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=25).

Units: percent cover. Reference period: 2000.

`prepare_glc_pc(source_lock)`:

Read GLC2000; for requested class 01-22 compute 100*class_area/support_area. Digits identify classes, not months.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
glc_pc_s01(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='01')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s02(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='02')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s03(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='03')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s04(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='04')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s05(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='05')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s06(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='06')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s07(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='07')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s08(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='08')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s09(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='09')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s10(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='10')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s11(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='11')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s12(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='12')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s13(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='13')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s14(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='14')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s15(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='15')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s16(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='16')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s17(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='17')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s18(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='18')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s19(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='19')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s20(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='20')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s21(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='21')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_s22(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='22')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u01(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='01')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u02(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='02')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u03(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='03')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u04(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='04')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u05(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='05')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u06(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='06')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u07(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='07')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u08(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='08')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u09(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='09')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u10(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='10')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u11(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='11')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u12(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='12')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u13(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='13')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u14(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='14')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u15(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='15')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u16(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='16')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u17(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='17')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u18(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='18')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u19(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='19')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u20(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='20')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u21(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='21')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

```text
glc_pc_u22(basin, source_lock):
    field = prepare_glc_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='22')
    return encode_and_validate(value, catalogue='L02', run_manifest=True)
```

## H10 ? gwt

Source: Global Groundwater Map; Fan et al. 2013. [Catalogue page 11](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=11).

Units: centimeters. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_gwt(source_lock)`:

Load Fan et al. modeled groundwater depth surface; mean valid cells in the local basin; convert source depth to centimeters. Mixed historical observations are not an annual time series.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
gwt_cm_sav(basin, source_lock):
    field = prepare_gwt(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='H10', run_manifest=True)
```

## A09 ? hdi

Source: Human Development Index (HDI) v2; Kummu et al. 2018. [Catalogue page 57](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=57).

Units: index value (x1000). Reference period: 2015.

`prepare_hdi(source_lock)`:

Read HDI v2 2015 surface; spatial mean and original scaling. Source interpolated historical years must retain modeled/interpolated provenance.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
hdi_ix_sav(basin, source_lock):
    field = prepare_hdi(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='A09', run_manifest=True)
```

## A06 ? hft

Source: Global Human Footprint v2; Venter et al. 2016. [Catalogue page 54](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=54).

Units: index value (x10). Reference period: 1993 / 2009.

`prepare_hft(source_lock)`:

Select 1993 or 2009 Human Footprint v2 field from suffix 93/09; spatial mean then x10 encoding. The suffix is a year, not a month.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
hft_ix_s09(basin, source_lock):
    field = prepare_hft(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='09')
    return encode_and_validate(value, catalogue='A06', run_manifest=True)
```

```text
hft_ix_s93(basin, source_lock):
    field = prepare_hft(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='93')
    return encode_and_validate(value, catalogue='A06', run_manifest=True)
```

```text
hft_ix_u09(basin, source_lock):
    field = prepare_hft(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='09')
    return encode_and_validate(value, catalogue='A06', run_manifest=True)
```

```text
hft_ix_u93(basin, source_lock):
    field = prepare_hft(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='93')
    return encode_and_validate(value, catalogue='A06', run_manifest=True)
```

## H03 ? inu

Source: Global Inundation Extent from Multi-Satellites (GIEMS-D15); Fluet-Chouinard et al. 2015. [Catalogue page 4](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=4).

Units: percent cover. Reference period: 1993-2004.

`prepare_inu(source_lock)`:

Select GIEMS-D15 mean annual minimum, mean annual maximum or long-term maximum extent for 1993-2004 according to mn/mx/lt; derive inundated area fraction in the selected support.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
inu_pc_slt(basin, source_lock):
    field = prepare_inu(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='lt')
    return encode_and_validate(value, catalogue='H03', run_manifest=True)
```

```text
inu_pc_smn(basin, source_lock):
    field = prepare_inu(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mn')
    return encode_and_validate(value, catalogue='H03', run_manifest=True)
```

```text
inu_pc_smx(basin, source_lock):
    field = prepare_inu(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mx')
    return encode_and_validate(value, catalogue='H03', run_manifest=True)
```

```text
inu_pc_ult(basin, source_lock):
    field = prepare_inu(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='lt')
    return encode_and_validate(value, catalogue='H03', run_manifest=True)
```

```text
inu_pc_umn(basin, source_lock):
    field = prepare_inu(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mn')
    return encode_and_validate(value, catalogue='H03', run_manifest=True)
```

```text
inu_pc_umx(basin, source_lock):
    field = prepare_inu(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mx')
    return encode_and_validate(value, catalogue='H03', run_manifest=True)
```

## L10 ? ire

Source: Historical Irrigation Dataset (HID) v1.0; Siebert et al. 2015. [Catalogue page 33](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=33).

Units: percent cover. Reference period: 2005.

`prepare_ire(source_lock)`:

Read HID v1.0 AEI_EARTHSTAT_IR_2005; convert area equipped for irrigation to support-area percentage with conservative allocation. Equipped area is not actual annual irrigation.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
ire_pc_sse(basin, source_lock):
    field = prepare_ire(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='L10', run_manifest=True)
```

```text
ire_pc_use(basin, source_lock):
    field = prepare_ire(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='L10', run_manifest=True)
```

## S07 ? kar

Source: World Map of Carbonate Rock Outcrops v3.0; Williams & Ford 2006. [Catalogue page 47](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=47).

Units: percent cover. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_kar(source_lock)`:

Use carbonate outcrop map v3; resolve inclusion of continuous/discontinuous carbonate classes; calculate mapped outcrop fraction, not all subsurface karst.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
kar_pc_sse(basin, source_lock):
    field = prepare_kar(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='S07', run_manifest=True)
```

```text
kar_pc_use(basin, source_lock):
    field = prepare_kar(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='S07', run_manifest=True)
```

## S06 ? lit

Source: Global Lithological Map (GLiM); Hartmann & Moosdorf 2012. [Catalogue page 46](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=46).

Units: classes (16). Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_lit(source_lock)`:

Use simplified GLiM 30-arc-minute grid, not full-resolution polygons; select majority among 16 lithological classes.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
lit_cl_smj(basin, source_lock):
    field = prepare_lit(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mj')
    return encode_and_validate(value, catalogue='S06', run_manifest=True)
```

## H04 ? lka

Source: HydroLAKES; Messager et al. 2016. [Catalogue page 5](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=5).

Units: percent cover (x10). Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_lka(source_lock)`:

Use HydroLAKES lake outlines from the pinned release; compute non-overlapping lake area as percent of support area under the original rasterization.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
lka_pc_sse(basin, source_lock):
    field = prepare_lka(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='H04', run_manifest=True)
```

```text
lka_pc_use(basin, source_lock):
    field = prepare_lka(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='H04', run_manifest=True)
```

## H05 ? lkv

Source: HydroLAKES; Messager et al. 2016. [Catalogue page 6](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=6).

Units: million cubic meters. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_lkv(source_lock)`:

Assign each HydroLAKES lake once through its co-registered outlet; sum lake volume over the upstream network; convert to million cubic meters. Do not count a lake once per intersected basin.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
lkv_mc_usu(basin, source_lock):
    field = prepare_lkv(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='su')
    return encode_and_validate(value, catalogue='H05', run_manifest=True)
```

## A04 ? nli

Source: DMSP-OLS Nighttime Lights v4; Doll 2008. [Catalogue page 52](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=52).

Units: index value (x100). Reference period: 2008.

`prepare_nli(source_lock)`:

Read 2008 DMSP-OLS v4 average-visible-times-frequency composite; spatial mean and x100 encoding. Do not substitute a different stable-lights band or uncalibrated VIIRS.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
nli_ix_sav(basin, source_lock):
    field = prepare_nli(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='A04', run_manifest=True)
```

```text
nli_ix_uav(basin, source_lock):
    field = prepare_nli(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='A04', run_manifest=True)
```

## L13 ? pac

Source: World Database on Protected Areas (WDPA); IUCN & UNEP-WCMC 2014. [Catalogue page 36](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=36).

Units: percent cover. Reference period: 2014-10.

`prepare_pac(source_lock)`:

Filter October-2014 WDPA to nationally designated sites and stated IUCN categories; convert point-only sites to equal-area circles using reported area; union overlaps and calculate protected fraction. Record point approximation.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
pac_pc_sse(basin, source_lock):
    field = prepare_pac(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='L13', run_manifest=True)
```

```text
pac_pc_use(basin, source_lock):
    field = prepare_pac(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='L13', run_manifest=True)
```

## C05 ? pet

Source: Global-PET v1; Zomer et al. 2008. [Catalogue page 19](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=19).

Units: millimeters. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_pet(source_lock)`:

Load Global-PET v1 monthly/annual surfaces (Hargreaves method driven by WorldClim); select period then spatial mean. A reconstruction of PET itself requires the original Hargreaves parameterization.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
pet_mm_s01(basin, source_lock):
    field = prepare_pet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='01')
    return encode_and_validate(value, catalogue='C05', run_manifest=True)
```

```text
pet_mm_s02(basin, source_lock):
    field = prepare_pet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='02')
    return encode_and_validate(value, catalogue='C05', run_manifest=True)
```

```text
pet_mm_s03(basin, source_lock):
    field = prepare_pet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='03')
    return encode_and_validate(value, catalogue='C05', run_manifest=True)
```

```text
pet_mm_s04(basin, source_lock):
    field = prepare_pet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='04')
    return encode_and_validate(value, catalogue='C05', run_manifest=True)
```

```text
pet_mm_s05(basin, source_lock):
    field = prepare_pet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='05')
    return encode_and_validate(value, catalogue='C05', run_manifest=True)
```

```text
pet_mm_s06(basin, source_lock):
    field = prepare_pet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='06')
    return encode_and_validate(value, catalogue='C05', run_manifest=True)
```

```text
pet_mm_s07(basin, source_lock):
    field = prepare_pet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='07')
    return encode_and_validate(value, catalogue='C05', run_manifest=True)
```

```text
pet_mm_s08(basin, source_lock):
    field = prepare_pet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='08')
    return encode_and_validate(value, catalogue='C05', run_manifest=True)
```

```text
pet_mm_s09(basin, source_lock):
    field = prepare_pet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='09')
    return encode_and_validate(value, catalogue='C05', run_manifest=True)
```

```text
pet_mm_s10(basin, source_lock):
    field = prepare_pet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='10')
    return encode_and_validate(value, catalogue='C05', run_manifest=True)
```

```text
pet_mm_s11(basin, source_lock):
    field = prepare_pet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='11')
    return encode_and_validate(value, catalogue='C05', run_manifest=True)
```

```text
pet_mm_s12(basin, source_lock):
    field = prepare_pet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='12')
    return encode_and_validate(value, catalogue='C05', run_manifest=True)
```

```text
pet_mm_syr(basin, source_lock):
    field = prepare_pet(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='yr')
    return encode_and_validate(value, catalogue='C05', run_manifest=True)
```

```text
pet_mm_uyr(basin, source_lock):
    field = prepare_pet(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='yr')
    return encode_and_validate(value, catalogue='C05', run_manifest=True)
```

## L03 ? pnv-cl

Source: EarthStat; Ramankutty & Foley 1999. [Catalogue page 26](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=26).

Units: classes (15). Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_pnv_cl(source_lock)`:

Read EarthStat potential natural vegetation 15-class map; select majority; retain its counterfactual vegetation meaning.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
pnv_cl_smj(basin, source_lock):
    field = prepare_pnv_cl(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mj')
    return encode_and_validate(value, catalogue='L03', run_manifest=True)
```

## L04 ? pnv-pc

Source: EarthStat; Ramankutty & Foley 1999. [Catalogue page 27](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=27).

Units: percent cover. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_pnv_pc(source_lock)`:

For requested EarthStat potential vegetation class 01-15 calculate class area percentage. This is potential vegetation, not annual observed land cover.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
pnv_pc_s01(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='01')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_s02(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='02')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_s03(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='03')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_s04(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='04')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_s05(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='05')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_s06(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='06')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_s07(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='07')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_s08(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='08')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_s09(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='09')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_s10(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='10')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_s11(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='11')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_s12(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='12')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_s13(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='13')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_s14(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='14')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_s15(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='15')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_u01(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='01')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_u02(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='02')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_u03(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='03')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_u04(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='04')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_u05(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='05')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_u06(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='06')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_u07(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='07')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_u08(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='08')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_u09(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='09')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_u10(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='10')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_u11(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='11')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_u12(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='12')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_u13(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='13')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_u14(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='14')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

```text
pnv_pc_u15(basin, source_lock):
    field = prepare_pnv_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='15')
    return encode_and_validate(value, catalogue='L04', run_manifest=True)
```

## A01 ? pop

Source: Gridded Population of the World (GPW) v4; CIESIN 2016. [Catalogue page 49](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=49).

Units: count (thousands). Reference period: 2010.

`prepare_pop(source_lock)`:

Read GPWv4 2010 population counts; conservatively allocate cell totals and sum local/upstream population; export in thousands of people.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
pop_ct_ssu(basin, source_lock):
    field = prepare_pop(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='su')
    return encode_and_validate(value, catalogue='A01', run_manifest=True)
```

```text
pop_ct_usu(basin, source_lock):
    field = prepare_pop(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='su')
    return encode_and_validate(value, catalogue='A01', run_manifest=True)
```

## A02 ? ppd

Source: Gridded Population of the World (GPW) v4; CIESIN 2016. [Catalogue page 50](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=50).

Units: people per km². Reference period: 2010.

`prepare_ppd(source_lock)`:

Read GPWv4 2010 population density; reproduce original density surface/mask and spatial mean in people/km2; check against count and documented area convention.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
ppd_pk_sav(basin, source_lock):
    field = prepare_ppd(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='A02', run_manifest=True)
```

```text
ppd_pk_uav(basin, source_lock):
    field = prepare_ppd(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='A02', run_manifest=True)
```

## C04 ? pre

Source: WorldClim v1.4; Hijmans et al. 2005. [Catalogue page 18](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=18).

Units: millimeters. Reference period: 1950-2000 source climatology.

`prepare_pre(source_lock)`:

Load WorldClim v1.4 monthly precipitation normals; select month or annual precipitation total field before spatial mean. Annual precipitation is a total across months, not their arithmetic mean.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
pre_mm_s01(basin, source_lock):
    field = prepare_pre(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='01')
    return encode_and_validate(value, catalogue='C04', run_manifest=True)
```

```text
pre_mm_s02(basin, source_lock):
    field = prepare_pre(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='02')
    return encode_and_validate(value, catalogue='C04', run_manifest=True)
```

```text
pre_mm_s03(basin, source_lock):
    field = prepare_pre(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='03')
    return encode_and_validate(value, catalogue='C04', run_manifest=True)
```

```text
pre_mm_s04(basin, source_lock):
    field = prepare_pre(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='04')
    return encode_and_validate(value, catalogue='C04', run_manifest=True)
```

```text
pre_mm_s05(basin, source_lock):
    field = prepare_pre(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='05')
    return encode_and_validate(value, catalogue='C04', run_manifest=True)
```

```text
pre_mm_s06(basin, source_lock):
    field = prepare_pre(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='06')
    return encode_and_validate(value, catalogue='C04', run_manifest=True)
```

```text
pre_mm_s07(basin, source_lock):
    field = prepare_pre(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='07')
    return encode_and_validate(value, catalogue='C04', run_manifest=True)
```

```text
pre_mm_s08(basin, source_lock):
    field = prepare_pre(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='08')
    return encode_and_validate(value, catalogue='C04', run_manifest=True)
```

```text
pre_mm_s09(basin, source_lock):
    field = prepare_pre(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='09')
    return encode_and_validate(value, catalogue='C04', run_manifest=True)
```

```text
pre_mm_s10(basin, source_lock):
    field = prepare_pre(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='10')
    return encode_and_validate(value, catalogue='C04', run_manifest=True)
```

```text
pre_mm_s11(basin, source_lock):
    field = prepare_pre(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='11')
    return encode_and_validate(value, catalogue='C04', run_manifest=True)
```

```text
pre_mm_s12(basin, source_lock):
    field = prepare_pre(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='12')
    return encode_and_validate(value, catalogue='C04', run_manifest=True)
```

```text
pre_mm_syr(basin, source_lock):
    field = prepare_pre(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='yr')
    return encode_and_validate(value, catalogue='C04', run_manifest=True)
```

```text
pre_mm_uyr(basin, source_lock):
    field = prepare_pre(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='yr')
    return encode_and_validate(value, catalogue='C04', run_manifest=True)
```

## L12 ? prm

Source: Permafrost Zonation Index (PZI); Gruber 2012. [Catalogue page 35](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=35).

Units: percent cover. Reference period: 1961-1990 model basis.

`prepare_prm(source_lock)`:

Read PZI based on 1961-1990 climate; resolve the published PZI-to-extent conversion before area reduction; do not invent a binary threshold or call it annual observed permafrost.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
prm_pc_sse(basin, source_lock):
    field = prepare_prm(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='L12', run_manifest=True)
```

```text
prm_pc_use(basin, source_lock):
    field = prepare_prm(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='L12', run_manifest=True)
```

## L09 ? pst

Source: EarthStat; Ramankutty et al. 2008. [Catalogue page 32](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=32).

Units: percent cover. Reference period: circa 2000.

`prepare_pst(source_lock)`:

Read EarthStat circa-2000 pasture fractions; area-weight fractions over support and express as percent.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
pst_pc_sse(basin, source_lock):
    field = prepare_pst(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='L09', run_manifest=True)
```

```text
pst_pc_use(basin, source_lock):
    field = prepare_pst(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='L09', run_manifest=True)
```

## A05 ? rdd

Source: Global Roads Inventory Project (GRIP) v4; Meijer et al. 2018. [Catalogue page 53](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=53).

Units: meters per km². Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_rdd(source_lock)`:

Read GRIP v4 all-road-type density grid at 5 arc-minutes; area mean in meters/km2. Vector road-length reconstruction requires a separate equivalence check.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
rdd_mk_sav(basin, source_lock):
    field = prepare_rdd(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='A05', run_manifest=True)
```

```text
rdd_mk_uav(basin, source_lock):
    field = prepare_rdd(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='A05', run_manifest=True)
```

## H06 ? rev

Source: Global Reservoir and Dams (GRanD) database v1.1; Lehner et al. 2011. [Catalogue page 7](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=7).

Units: million cubic meters. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_rev(source_lock)`:

Assign GRanD v1.1 reservoirs to the drainage network; accumulate unique upstream reservoir capacities in million cubic meters. Capacity is not annual observed storage.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
rev_mc_usu(basin, source_lock):
    field = prepare_rev(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='su')
    return encode_and_validate(value, catalogue='H06', run_manifest=True)
```

## H08 ? ria

Source: HydroSHEDS and WaterGAP v2.2; Lehner & Grill 2013. [Catalogue page 9](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=9).

Units: hectares. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_ria(source_lock)`:

Use HydroSHEDS reach length and WaterGAP 1971-2000 monthly maximum discharge as bankfull proxy; apply Allen et al. hydraulic-width relation; sum width*length over unique reaches; convert m2 to hectares. Pin published coefficients before execution.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
ria_ha_ssu(basin, source_lock):
    field = prepare_ria(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='su')
    return encode_and_validate(value, catalogue='H08', run_manifest=True)
```

```text
ria_ha_usu(basin, source_lock):
    field = prepare_ria(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='su')
    return encode_and_validate(value, catalogue='H08', run_manifest=True)
```

## H09 ? riv

Source: HydroSHEDS and WaterGAP v2.2; Lehner & Grill 2013. [Catalogue page 10](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=10).

Units: thousand cubic meters. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_riv(source_lock)`:

Use the same bankfull proxy and reach lengths as ria; apply published hydraulic width and depth relations; sum width*depth*length; convert m3 to thousands of m3. Pin coefficients and reach assignment.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
riv_tc_ssu(basin, source_lock):
    field = prepare_riv(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='su')
    return encode_and_validate(value, catalogue='H09', run_manifest=True)
```

```text
riv_tc_usu(basin, source_lock):
    field = prepare_riv(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='su')
    return encode_and_validate(value, catalogue='H09', run_manifest=True)
```

## H02 ? run

Source: WaterGAP v2.2 (data of 2014); Döll et al. 2003. [Catalogue page 3](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=3).

Units: millimeters. Reference period: 1971-2000.

`prepare_run(source_lock)`:

Load WaterGAP 2.2 (2014) long-term runoff depth, 1971-2000; reproduce downscaling; calculate local basin mean annual depth, not a sum of depths.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
run_mm_syr(basin, source_lock):
    field = prepare_run(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='yr')
    return encode_and_validate(value, catalogue='H02', run_manifest=True)
```

## P03 ? sgr

Source: EarthEnv-DEM90; Robinson et al. 2014. [Catalogue page 14](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=14).

Units: decimeters per km. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_sgr(source_lock)`:

Lift single-cell DEM sinks to the minimum neighboring elevation; minimum-aggregate 3 to 15 arc-seconds; reach gradient=(maximum-minimum reach elevation)/reach length. Resolve the reach-to-basin weighting before execution.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
sgr_dk_sav(basin, source_lock):
    field = prepare_sgr(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='P03', run_manifest=True)
```

## P02 ? slp

Source: EarthEnv-DEM90; Robinson et al. 2014. [Catalogue page 13](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=13).

Units: degrees (x10). Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_slp(source_lock)`:

Calculate Horn slope on 3-arc-second EarthEnv-DEM90 with latitude-corrected geodesic XY spacing; mean-aggregate slope to 15 arc-seconds; reduce over basin/support; export degrees with catalogue scaling.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
slp_dg_sav(basin, source_lock):
    field = prepare_slp(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='P02', run_manifest=True)
```

```text
slp_dg_uav(basin, source_lock):
    field = prepare_slp(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='P02', run_manifest=True)
```

## S02 ? slt

Source: SoilGrids1km; Hengl et al. 2014. [Catalogue page 42](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=42).

Units: percent. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_slt(source_lock)`:

Select SoilGrids1km silt fraction at 0-5 cm; spatial mean over valid support, retain percent units.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
slt_pc_sav(basin, source_lock):
    field = prepare_slt(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='S02', run_manifest=True)
```

```text
slt_pc_uav(basin, source_lock):
    field = prepare_slt(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='S02', run_manifest=True)
```

## S03 ? snd

Source: SoilGrids1km; Hengl et al. 2014. [Catalogue page 43](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=43).

Units: percent. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_snd(source_lock)`:

Select SoilGrids1km sand fraction at 0-5 cm; spatial mean over valid support, retain percent units.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
snd_pc_sav(basin, source_lock):
    field = prepare_snd(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='S03', run_manifest=True)
```

```text
snd_pc_uav(basin, source_lock):
    field = prepare_snd(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='S03', run_manifest=True)
```

## C09 ? snw

Source: MODIS/Aqua Snow Cover (MYD10CM); Hall & Riggs 2016. [Catalogue page 23](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=23).

Units: percent cover. Reference period: 2002-07/2015-04.

`prepare_snw(source_lock)`:

Resolve C09 MYD10CM-heading versus MYD10A1-v6-daily provenance; apply documented snow QA, cloud/night masks and monthly compositing to July 2002-April 2015; form monthly climatology and requested annual mean/maximum before basin reduction. Report observed area/time coverage.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
snw_pc_s01(basin, source_lock):
    field = prepare_snw(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='01')
    return encode_and_validate(value, catalogue='C09', run_manifest=True)
```

```text
snw_pc_s02(basin, source_lock):
    field = prepare_snw(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='02')
    return encode_and_validate(value, catalogue='C09', run_manifest=True)
```

```text
snw_pc_s03(basin, source_lock):
    field = prepare_snw(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='03')
    return encode_and_validate(value, catalogue='C09', run_manifest=True)
```

```text
snw_pc_s04(basin, source_lock):
    field = prepare_snw(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='04')
    return encode_and_validate(value, catalogue='C09', run_manifest=True)
```

```text
snw_pc_s05(basin, source_lock):
    field = prepare_snw(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='05')
    return encode_and_validate(value, catalogue='C09', run_manifest=True)
```

```text
snw_pc_s06(basin, source_lock):
    field = prepare_snw(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='06')
    return encode_and_validate(value, catalogue='C09', run_manifest=True)
```

```text
snw_pc_s07(basin, source_lock):
    field = prepare_snw(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='07')
    return encode_and_validate(value, catalogue='C09', run_manifest=True)
```

```text
snw_pc_s08(basin, source_lock):
    field = prepare_snw(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='08')
    return encode_and_validate(value, catalogue='C09', run_manifest=True)
```

```text
snw_pc_s09(basin, source_lock):
    field = prepare_snw(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='09')
    return encode_and_validate(value, catalogue='C09', run_manifest=True)
```

```text
snw_pc_s10(basin, source_lock):
    field = prepare_snw(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='10')
    return encode_and_validate(value, catalogue='C09', run_manifest=True)
```

```text
snw_pc_s11(basin, source_lock):
    field = prepare_snw(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='11')
    return encode_and_validate(value, catalogue='C09', run_manifest=True)
```

```text
snw_pc_s12(basin, source_lock):
    field = prepare_snw(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='12')
    return encode_and_validate(value, catalogue='C09', run_manifest=True)
```

```text
snw_pc_smx(basin, source_lock):
    field = prepare_snw(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mx')
    return encode_and_validate(value, catalogue='C09', run_manifest=True)
```

```text
snw_pc_syr(basin, source_lock):
    field = prepare_snw(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='yr')
    return encode_and_validate(value, catalogue='C09', run_manifest=True)
```

```text
snw_pc_uyr(basin, source_lock):
    field = prepare_snw(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='yr')
    return encode_and_validate(value, catalogue='C09', run_manifest=True)
```

## S04 ? soc

Source: SoilGrids1km; Hengl et al. 2014. [Catalogue page 44](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=44).

Units: tonnes/hectare. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_soc(source_lock)`:

Select SoilGrids1km soil organic carbon stock at 0-5 cm; spatial mean in tonnes per hectare; do not substitute concentration or a deeper soil layer.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
soc_th_sav(basin, source_lock):
    field = prepare_soc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='S04', run_manifest=True)
```

```text
soc_th_uav(basin, source_lock):
    field = prepare_soc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='av')
    return encode_and_validate(value, catalogue='S04', run_manifest=True)
```

## S05 ? swc

Source: Global High-Resolution Soil-Water Balance; Trabucco & Zomer 2010. [Catalogue page 45](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=45).

Units: percent. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_swc(source_lock)`:

Select monthly/annual Global Soil-Water Balance fraction of maximum available soil water; area mean in percent. This is a stress-related fraction, not volumetric soil moisture.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
swc_pc_s01(basin, source_lock):
    field = prepare_swc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='01')
    return encode_and_validate(value, catalogue='S05', run_manifest=True)
```

```text
swc_pc_s02(basin, source_lock):
    field = prepare_swc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='02')
    return encode_and_validate(value, catalogue='S05', run_manifest=True)
```

```text
swc_pc_s03(basin, source_lock):
    field = prepare_swc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='03')
    return encode_and_validate(value, catalogue='S05', run_manifest=True)
```

```text
swc_pc_s04(basin, source_lock):
    field = prepare_swc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='04')
    return encode_and_validate(value, catalogue='S05', run_manifest=True)
```

```text
swc_pc_s05(basin, source_lock):
    field = prepare_swc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='05')
    return encode_and_validate(value, catalogue='S05', run_manifest=True)
```

```text
swc_pc_s06(basin, source_lock):
    field = prepare_swc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='06')
    return encode_and_validate(value, catalogue='S05', run_manifest=True)
```

```text
swc_pc_s07(basin, source_lock):
    field = prepare_swc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='07')
    return encode_and_validate(value, catalogue='S05', run_manifest=True)
```

```text
swc_pc_s08(basin, source_lock):
    field = prepare_swc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='08')
    return encode_and_validate(value, catalogue='S05', run_manifest=True)
```

```text
swc_pc_s09(basin, source_lock):
    field = prepare_swc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='09')
    return encode_and_validate(value, catalogue='S05', run_manifest=True)
```

```text
swc_pc_s10(basin, source_lock):
    field = prepare_swc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='10')
    return encode_and_validate(value, catalogue='S05', run_manifest=True)
```

```text
swc_pc_s11(basin, source_lock):
    field = prepare_swc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='11')
    return encode_and_validate(value, catalogue='S05', run_manifest=True)
```

```text
swc_pc_s12(basin, source_lock):
    field = prepare_swc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='12')
    return encode_and_validate(value, catalogue='S05', run_manifest=True)
```

```text
swc_pc_syr(basin, source_lock):
    field = prepare_swc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='yr')
    return encode_and_validate(value, catalogue='S05', run_manifest=True)
```

```text
swc_pc_uyr(basin, source_lock):
    field = prepare_swc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='yr')
    return encode_and_validate(value, catalogue='S05', run_manifest=True)
```

## L14 ? tbi

Source: Terrestrial Ecoregions of the World (TEOW); Dinerstein et al. 2017. [Catalogue page 37](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=37).

Units: classes (14). Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_tbi(source_lock)`:

Read the updated TEOW/Dinerstein-2017 map; reclassify to 14 biomes using pinned legend then select majority biome.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
tbi_cl_smj(basin, source_lock):
    field = prepare_tbi(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mj')
    return encode_and_validate(value, catalogue='L14', run_manifest=True)
```

## L15 ? tec

Source: Terrestrial Ecoregions of the World (TEOW); Dinerstein et al. 2017. [Catalogue page 38](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=38).

Units: classes (846). Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_tec(source_lock)`:

Read the updated TEOW/Dinerstein-2017 ecoregion map; select majority ecoregion ID under the atlas legend.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
tec_cl_smj(basin, source_lock):
    field = prepare_tec(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mj')
    return encode_and_validate(value, catalogue='L15', run_manifest=True)
```

## C03 ? tmp

Source: WorldClim v1.4; Hijmans et al. 2005. [Catalogue page 17](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=17).

Units: degrees Celsius (x10). Reference period: 1950-2000 source climatology.

`prepare_tmp(source_lock)`:

Load WorldClim v1.4 temperature normals; choose mean, minimum or maximum temperature input as specified in C03 before spatial reduction. Resolve extreme-field construction; do not take spatial min/max for temperature suffix mn/mx.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
tmp_dc_s01(basin, source_lock):
    field = prepare_tmp(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='01')
    return encode_and_validate(value, catalogue='C03', run_manifest=True)
```

```text
tmp_dc_s02(basin, source_lock):
    field = prepare_tmp(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='02')
    return encode_and_validate(value, catalogue='C03', run_manifest=True)
```

```text
tmp_dc_s03(basin, source_lock):
    field = prepare_tmp(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='03')
    return encode_and_validate(value, catalogue='C03', run_manifest=True)
```

```text
tmp_dc_s04(basin, source_lock):
    field = prepare_tmp(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='04')
    return encode_and_validate(value, catalogue='C03', run_manifest=True)
```

```text
tmp_dc_s05(basin, source_lock):
    field = prepare_tmp(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='05')
    return encode_and_validate(value, catalogue='C03', run_manifest=True)
```

```text
tmp_dc_s06(basin, source_lock):
    field = prepare_tmp(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='06')
    return encode_and_validate(value, catalogue='C03', run_manifest=True)
```

```text
tmp_dc_s07(basin, source_lock):
    field = prepare_tmp(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='07')
    return encode_and_validate(value, catalogue='C03', run_manifest=True)
```

```text
tmp_dc_s08(basin, source_lock):
    field = prepare_tmp(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='08')
    return encode_and_validate(value, catalogue='C03', run_manifest=True)
```

```text
tmp_dc_s09(basin, source_lock):
    field = prepare_tmp(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='09')
    return encode_and_validate(value, catalogue='C03', run_manifest=True)
```

```text
tmp_dc_s10(basin, source_lock):
    field = prepare_tmp(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='10')
    return encode_and_validate(value, catalogue='C03', run_manifest=True)
```

```text
tmp_dc_s11(basin, source_lock):
    field = prepare_tmp(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='11')
    return encode_and_validate(value, catalogue='C03', run_manifest=True)
```

```text
tmp_dc_s12(basin, source_lock):
    field = prepare_tmp(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='12')
    return encode_and_validate(value, catalogue='C03', run_manifest=True)
```

```text
tmp_dc_smn(basin, source_lock):
    field = prepare_tmp(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mn')
    return encode_and_validate(value, catalogue='C03', run_manifest=True)
```

```text
tmp_dc_smx(basin, source_lock):
    field = prepare_tmp(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mx')
    return encode_and_validate(value, catalogue='C03', run_manifest=True)
```

```text
tmp_dc_syr(basin, source_lock):
    field = prepare_tmp(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='yr')
    return encode_and_validate(value, catalogue='C03', run_manifest=True)
```

```text
tmp_dc_uyr(basin, source_lock):
    field = prepare_tmp(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='yr')
    return encode_and_validate(value, catalogue='C03', run_manifest=True)
```

## A03 ? urb

Source: Global Human Settlement (GHS) Settlement Model v1.0 (2016); Pesaresi & Freire 2016. [Catalogue page 51](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=51).

Units: percent cover. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_urb(source_lock)`:

Select the original GHS-SMOD 2016 release and atlas epoch; resolve urban class selection from the source legend; calculate selected urban fraction. Built-up fraction is a distinct measure.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
urb_pc_sse(basin, source_lock):
    field = prepare_urb(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='A03', run_manifest=True)
```

```text
urb_pc_use(basin, source_lock):
    field = prepare_urb(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='se')
    return encode_and_validate(value, catalogue='A03', run_manifest=True)
```

## L05 ? wet-cl

Source: Global Lakes and Wetlands Database (GLWD); Lehner & Döll 2004. [Catalogue page 28](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=28).

Units: classes (12). Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_wet_cl(source_lock)`:

Read GLWD 30-arc-second wetland grid; exclude non-wetland cells when selecting majority; no wetlands maps to original -9999, normalized to null with reason internally.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
wet_cl_smj(basin, source_lock):
    field = prepare_wet_cl(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='mj')
    return encode_and_validate(value, catalogue='L05', run_manifest=True)
```

## L06 ? wet-pc

Source: Global Lakes and Wetlands Database (GLWD); Lehner & Döll 2004. [Catalogue page 29](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=29).

Units: percent cover. Reference period: Mixed/source-specific; resolve exact release and observation period before execution.

`prepare_wet_pc(source_lock)`:

Read GLWD; classes 01-09 are individual extents; g1 combines 1-12 and g2 combines 4-12. Resolve fractional classes 10-12 treatment against legend before deriving grouped area fractions.

Review gates: Pin original input assets and release hashes; Confirm original grid/mask, temporal reduction, scaling, rounding and nodata; Set attribute-specific comparison tolerances before running.

```text
wet_pc_s01(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='01')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_s02(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='02')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_s03(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='03')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_s04(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='04')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_s05(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='05')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_s06(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='06')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_s07(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='07')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_s08(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='08')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_s09(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='09')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_sg1(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='g1')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_sg2(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 's', pinned_geometry)
    value = reduce_per_source(field, support, dimension='g2')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_u01(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='01')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_u02(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='02')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_u03(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='03')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_u04(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='04')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_u05(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='05')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_u06(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='06')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_u07(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='07')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_u08(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='08')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_u09(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='09')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_ug1(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='g1')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```

```text
wet_pc_ug2(basin, source_lock):
    field = prepare_wet_pc(source_lock)
    support = resolve_support(basin, 'u', pinned_geometry)
    value = reduce_per_source(field, support, dimension='g2')
    return encode_and_validate(value, catalogue='L06', run_manifest=True)
```
