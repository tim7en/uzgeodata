const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs=require('node:fs');
(async()=>{
 fs.mkdirSync('tmp',{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM || undefined});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const base=process.env.TEST_BASE_URL || 'http://127.0.0.1:5175';
  await page.goto(base+'/case-studies.html#sabitov-methods',{waitUntil:'networkidle'});
  const section=page.locator('#sabitov-methods');
  await section.getByRole('heading',{name:'Test the mountain-water processes.'}).waitFor();
  await section.getByText('Physical validation: unresolved.',{exact:true}).waitFor();
  for(const mode of ['flow','duration','paths','snow','et']){
   await section.getByLabel('Thesis hydrology chart').selectOption(mode);
   if(await section.locator('svg[role="img"]').count()<2)throw Error('Missing hydrology/scenario chart: '+mode);
  }
  await section.getByLabel('Thesis climate scenario model').selectOption('m3');
  await section.getByText('What changed from the thesis, and what is still missing?',{exact:true}).click();
  await section.getByRole('cell',{name:'Awaiting soil evidence',exact:true}).waitFor();
  for(const file of ['sabitov-methods-atlas.pdf','sabitov-methods-analysis.xlsx','sabitov-daily-predictions.csv']){
   const response=await page.request.get(base+'/data/case-studies/'+file);
   if(!response.ok() || (await response.body()).length<1000)throw Error('Missing artifact '+file);
  }
  await section.getByText('What changed from the thesis, and what is still missing?',{exact:true}).click();
  await section.getByLabel('Thesis hydrology chart').selectOption('flow');
  await section.scrollIntoViewIfNeeded();await page.screenshot({path:'tmp/sabitov-desktop.png'});
  await page.setViewportSize({width:390,height:844});
  await section.scrollIntoViewIfNeeded();
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+2);
  if(overflow)throw Error('Mobile page overflow');
  await page.screenshot({path:'tmp/sabitov-mobile.png'});
  if(errors.length)throw Error(errors.join('\n'));
  console.log('Sabitov browser: five hydrology views, scenario selector, method matrix, downloads and mobile layout passed.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
