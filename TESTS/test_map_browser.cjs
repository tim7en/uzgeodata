const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
require('node:fs').mkdirSync('tmp',{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM || undefined});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto((process.env.TEST_BASE_URL || 'http://127.0.0.1:5175')+'/',{waitUntil:'networkidle'});
 await page.locator('.land-level').filter({hasText:'Level 7'}).waitFor();
 await page.locator('.land-lake-symbol').first().waitFor();
 const canvas=await page.locator('.leaflet-marker-pane canvas').count();if(canvas)throw Error('Full-map marker canvas still present');
 // Browser mouse events must reach the canvas polygons, not directly fired Leaflet handlers.
 async function selectBasin(){
   for(const [x,y] of [[720,500],[780,470],[700,450],[820,520],[900,500]]){
    if(!await page.evaluate(({x,y})=>document.elementFromPoint(x,y)?.tagName==='CANVAS',{x,y}))continue;
    await page.mouse.click(x,y);await page.waitForTimeout(250);
    if(await page.getByRole('dialog',{name:'Atlas attributes for this basin'}).count())return;
    const other=page.getByRole('dialog');if(await other.count())await page.keyboard.press('Escape');
   }
   throw Error('No basin modal after real map clicks');
 }
 const levels=[];
 for(const [level,clicks] of [[7,0],[10,1],[12,2]]){
   for(let i=0;i<clicks;i++){await page.getByRole('button',{name:'Zoom in',exact:true}).click();await page.waitForTimeout(450);}
   console.log('After zoom',level,await page.locator('.land-level').textContent(),errors);
   await page.locator('.land-level').filter({hasText:`Level ${level}`}).waitFor({state:'attached'});
   await selectBasin();
   const dialog=page.getByRole('dialog',{name:'Atlas attributes for this basin'});
   await dialog.locator('tbody tr').first().waitFor();const rows=await dialog.locator('tbody tr').count();if(rows<200)throw Error('Attribute join incomplete');
   levels.push({level,rows});await page.keyboard.press('Escape');
 }
 await page.getByLabel('Dams and reservoirs',{exact:false}).uncheck();await selectBasin();await page.keyboard.press('Escape');
 await page.getByLabel('Dams and reservoirs',{exact:false}).check();await selectBasin();await page.keyboard.press('Escape');
 await page.getByLabel('Lakes and water surfaces',{exact:false}).uncheck();await selectBasin();await page.keyboard.press('Escape');
 await page.getByLabel('Lakes and water surfaces',{exact:false}).check();await page.locator('.land-lake-symbol').first().waitFor();
 // Target an actual visible lake icon (offscreen marker elements also exist).
 const marker=page.locator('.land-lake-symbol');let lakeOpened=false;
 for(let i=0;i<await marker.count();i++){const b=await marker.nth(i).boundingBox();if(b&&b.x>380&&b.x<1300&&b.y>180&&b.y<900){await marker.nth(i).click();lakeOpened=true;break;}}
 if(!lakeOpened)throw Error('No visible lake symbol tested');
 await page.getByRole('heading',{name:'Reservoir cross-reference',exact:true}).waitFor();await page.screenshot({path:'tmp/lake-modal.png'});await page.keyboard.press('Escape');
 await page.screenshot({path:'tmp/main-lakes-map.png'});
 const dams=page.locator('.leaflet-marker-pane > svg path.leaflet-interactive');let damOpened=false;
 for(let i=0;i<await dams.count();i++){const b=await dams.nth(i).boundingBox();if(b&&b.x>380&&b.x<1300&&b.y>180&&b.y<900){await dams.nth(i).click();await page.waitForTimeout(300);if(await page.getByRole('dialog',{name:/^Dam /}).count()){damOpened=true;break;}}}
 if(!damOpened)throw Error('Dam interaction missing');
 await page.getByRole('heading',{name:'Lake and reservoir cross-check',exact:true}).waitFor();await page.keyboard.press('Escape');
 for(const [level,clicks] of [[10,2],[7,1]]){
  for(let i=0;i<clicks;i++){await page.getByRole('button',{name:'Zoom out',exact:true}).click();await page.waitForTimeout(450);}
  await page.locator('.land-level').filter({hasText:`Level ${level}`}).waitFor({state:'attached'});await selectBasin();await page.keyboard.press('Escape');
 }
 await page.goto((process.env.TEST_BASE_URL || 'http://127.0.0.1:5175')+'/atlas.html',{waitUntil:'networkidle'});
 await page.locator('.atlas-map .leaflet-overlay-pane canvas').waitFor();
 if(await page.locator('.leaflet-marker-pane canvas').count())throw Error('Atlas marker canvas still present');
 await page.mouse.click(820,500);await page.waitForTimeout(400);
 await page.locator('.atlas-hit').waitFor();
 await page.goto((process.env.TEST_BASE_URL || 'http://127.0.0.1:5175')+'/',{waitUntil:'networkidle'});await page.setViewportSize({width:390,height:844});
 const width=await page.evaluate(()=>({view:innerWidth,content:document.documentElement.scrollWidth}));if(width.content>width.view)throw Error('Mobile overflow');
 console.log(JSON.stringify({levels,lakeOpened,damOpened,zoomOut:true,atlasSelection:true,mobile:width,errors}));if(errors.length)throw Error(errors.join('\n'));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
