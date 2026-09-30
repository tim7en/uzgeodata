// Scientific terms the portal renders itself instead of leaving to machine translation.
//
// Google Translate renders the English page on request, and for most prose that is
// acceptable. For the names of views, variables and evidence labels it is not: it made
// "Snow forecast" - a seasonal river-flow forecast from snow storage - into "weather
// forecast: snow", and "Monthly record" into "monthly report". A term listed here is
// written in the reader's language from this table and marked translate="no", so the
// machine translator leaves it alone; the English original stays in the title.
//
// STATUS: draft terms, not yet reviewed. They were written for this portal and need
// review by a hydrologist fluent in Russian and in Uzbek before they are treated as
// the portal's terminology. Record the reviewer and date in GLOSSARY_REVIEW when done.
import { activeLang } from './lang.js';

export const GLOSSARY_REVIEW = { status: 'draft', reviewed_by: null, reviewed_at: null };

export const GLOSSARY = {
  // Basin window tabs
  tab_original: { en: 'HydroATLAS attributes', ru: 'Атрибуты HydroATLAS', uz: 'HydroATLAS atributlari' },
  tab_substitutes: { en: 'Independent estimates', ru: 'Независимые оценки', uz: 'Mustaqil baholar' },
  tab_history: { en: 'Monthly record', ru: 'Помесячный ряд данных', uz: 'Oylik maʼlumotlar qatori' },
  tab_climate: { en: 'Recent climate', ru: 'Климат последних месяцев', uz: 'Soʻnggi oylar iqlimi' },
  tab_drought: { en: 'Drought & outlook', ru: 'Засуха и перспективы', uz: 'Qurgʻoqchilik va istiqbol' },
  tab_snow: { en: 'Snow forecast', ru: 'Прогноз стока по снегозапасам', uz: 'Qor zaxirasi boʻyicha oqim prognozi' },
  tab_catchment: { en: 'Catchment statistics', ru: 'Статистика водосбора', uz: 'Suv yigʻish havzasi statistikasi' },
  basin_assessment: { en: 'Basin assessment', ru: 'Оценка бассейна', uz: 'Havza bahosi' },
  water_year: { en: 'water year', ru: 'гидрологический год', uz: 'gidrologik yil' },

  // Monthly variables (history series keys)
  pre_mm_s: { en: 'Precipitation', ru: 'Осадки', uz: 'Yogʻingarchilik' },
  aet_mm_s: { en: 'Actual evapotranspiration', ru: 'Фактическое суммарное испарение', uz: 'Haqiqiy bugʻlanish (evapotranspiratsiya)' },
  pet_mm_s: { en: 'Potential evapotranspiration', ru: 'Потенциальное испарение', uz: 'Potensial bugʻlanish' },
  cwd_mm_s: { en: 'Climatic water deficit', ru: 'Климатический дефицит влаги', uz: 'Iqlimiy namlik taqchilligi' },
  soil_mm_s: { en: 'Soil moisture', ru: 'Влажность почвы', uz: 'Tuproq namligi' },
  swe_mm_s: { en: 'Snow water equivalent', ru: 'Снегозапас (водный эквивалент снега)', uz: 'Qor zaxirasi (suv ekvivalenti)' },
  snw_pc_s: { en: 'Snow cover', ru: 'Снежный покров', uz: 'Qor qoplami' },
  run_mm_s: { en: 'Runoff (ERA5-Land)', ru: 'Сток (ERA5-Land)', uz: 'Oqim (ERA5-Land)' },
  rtc_mm_s: { en: 'Runoff (TerraClimate)', ru: 'Сток (TerraClimate)', uz: 'Oqim (TerraClimate)' },
  tmp_dc_s: { en: 'Mean air temperature (ERA5-Land)', ru: 'Средняя температура воздуха (ERA5-Land)', uz: 'Oʻrtacha havo harorati (ERA5-Land)' },
  tmx_dc_s: { en: 'Maximum temperature', ru: 'Максимальная температура', uz: 'Maksimal harorat' },
  tmn_dc_s: { en: 'Minimum temperature', ru: 'Минимальная температура', uz: 'Minimal harorat' },
  vpd_kp_s: { en: 'Vapour pressure deficit', ru: 'Дефицит упругости водяного пара', uz: 'Suv bugʻi bosimi taqchilligi' },
  pds_ix_s: { en: 'Palmer drought index (PDSI)', ru: 'Индекс засухи Палмера (PDSI)', uz: 'Palmer qurgʻoqchilik indeksi (PDSI)' },

  // What an answer rests on (assessmentModel BASIS)
  basis_gridded: { en: 'Historical gridded data', ru: 'Исторические сеточные данные', uz: 'Tarixiy toʻrli maʼlumotlar' },
  basis_provisional: { en: 'Provisional estimates', ru: 'Предварительные оценки', uz: 'Dastlabki baholar' },
  basis_forecast: { en: 'Seasonal forecast', ru: 'Сезонный прогноз', uz: 'Mavsumiy prognoz' },
  basis_inventory: { en: 'Survey inventory', ru: 'Данные инвентаризации', uz: 'Inventarizatsiya maʼlumotlari' },
  basis_gauges: { en: 'Measured river flow (past years)', ru: 'Измеренный речной сток (прошлые годы)', uz: 'Oʻlchangan daryo oqimi (oʻtgan yillar)' },
  basis_none: { en: 'Not established', ru: 'Не установлено', uz: 'Aniqlanmagan' },
};

/** The term in `lang` (default: the page's language), falling back to English, then `fallback`. */
export function term(id, fallback = '', lang = safeLang()) {
  const entry = GLOSSARY[id];
  if (!entry) return fallback;
  return entry[lang] || entry.en || fallback;
}

/** Whether the glossary renders this language itself (so the translator must be kept off). */
export function rendersLanguage(lang = safeLang()) {
  return lang !== 'en' && Object.values(GLOSSARY).some(entry => entry[lang]);
}

function safeLang() {
  try { return activeLang(); } catch { return 'en'; }
}
