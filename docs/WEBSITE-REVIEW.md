# Public website review

The project is an exploratory basin atlas for the Amu Darya and Syr Darya systems.
Its strongest public task is finding a basin, comparing published attributes and
independent estimates, inspecting monthly records, and downloading the evidence.

## Findings and changes

- The interactive map remains the homepage. A separate `/project.html` explains
  purpose, coverage, tools, and development with a native accordion sidebar.
- Removed the automatic fit to all basins after data loading, which caused the map
  to zoom out on load. The map restores a saved center and zoom when available.
  Reset returns to the default location; explicit controls fit an individual basin
  or the polygons selected by an area of interest. Zoom-dependent detail is retained.
- The new `/examples.html` page gives three practical workflows: a basin profile,
  monthly-record exploration, and comparison of source estimates. Each specifies
  an expected output, steps, relevant limits, and links to actual example data.
- The About, Guide, and Projects pages use a consistent light reading style and
  connect back to the homepage, map, and examples. Projects distinguishes available
  work, next scientific priorities, and longer-term programmes.
- The saved monthly index already includes three temperature variables. Updated
  introductory text that incorrectly treated all temperature publication as pending.
- Geographic project-page artwork derives from the published level-seven reference
  basin polygons and main river network; it is an overview, not a new data product.

## Reference and content boundaries

The USGS StreamStats site (https://www.usgs.gov/streamstats) informed the separation
of project explanation, application access, guidance, and research examples.
UzGeoData is independent of USGS. StreamStats capabilities such as arbitrary-point
watershed delineation and estimated engineering flow statistics are not advertised
as UzGeoData capabilities.

No atlas attribute has passed independent scientific reproduction. Snow is withdrawn
from trend use. Published attributes and independent estimates remain distinguishable.
The roadmap describes research priorities without deadlines or implied completion.
Broader 2000–2026 historical ambitions are separate from the current monthly release.

## Verification

- All 124 Node UI/model tests pass, including persistence, invalid saved state,
  reset-state storage, and Polygon/MultiPolygon bounds handling.
- Launch builds pass at both `/` and `/uzgeodata/`, validating all 7,445 basin
  attribute/history records. Both builds pass 145 local navigation, asset,
  example-download, and anchor checks.
- Local preview responds at http://127.0.0.1:4173/; the project reader is at
  http://127.0.0.1:4173/project.html.
- Live HTTPS release metadata responds at https://uzgeodata.uz/release.json.
  `/project.html` returns 404 on the live site: these changes are not deployed.
- Browser validation remains outstanding: the Browser runtime reports no connected
  browsers. GitHub CLI is not authenticated, so authenticated Actions/Pages status
  and deployment are not available in this session.

Before publishing, verify the map holds its position while data loads and after
refresh, reset returns to the starting location, selected basin/AOI fit controls
work, and the accordion reader works on desktop and mobile. Deployment uses the
existing Pages workflow and the custom-domain root base `/`.
