# Basin and water-body interaction regression

Run the application, then `npm run test:map-browser`. This optional browser
check requires Playwright with Chromium. Set `TEST_BASE_URL` if the application
is not at `http://127.0.0.1:5175`. `PLAYWRIGHT_MODULE` can point to an existing
Playwright installation and `PLAYWRIGHT_CHROMIUM` to an existing browser binary.

The check sends real browser mouse clicks to the map. It verifies all 281 basin
attributes at levels 7, 10 and 12, zooming in and back out, with dam/lake overlays
on and off. It also opens lake and dam details, checks the atlas selection,
checks mobile page width, and fails on browser exceptions. Screenshots go to
ignored `tmp/`. Directly calling Leaflet feature handlers would not reproduce
the original stacked-canvas hit-testing bug.

The related data tests run with `npm run test:waterbody-review`; they guard native
identifiers, unconfirmed nearby candidates, missing names and zero storage.
