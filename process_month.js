const fs = require('fs');

module.exports = async (page) => {
  const path = '/home/jasondel/dev/coach/.processed_workouts.json';
  let processed = [];
  try { processed = JSON.parse(fs.readFileSync(path, 'utf8')); } catch(e) {}
  
  const activities = await page.locator('.activity .workoutDiv').all();
  let count = 0;
  for (const act of activities) {
     const id = await act.getAttribute('data-workoutid');
     if (!id || processed.includes(id)) continue;
     
     await act.click({force: true});
     await page.waitForTimeout(800);
     
     const filesBtn = page.getByRole('button', { name: 'Files' }).first();
     if (await filesBtn.count() > 0) {
         await filesBtn.click();
         await page.waitForTimeout(500);
         const downloadBtn = page.getByRole('button', { name: 'Download' }).first();
         if (await downloadBtn.count() > 0) {
             let dp = page.waitForEvent('download', { timeout: 2000 }).catch(()=>null);
             await downloadBtn.click();
             let dl = await dp;
             if (!dl) {
                 const cont = page.getByRole('button', { name: /Continue Download/i }).first();
                 if (await cont.count() > 0) {
                     dp = page.waitForEvent('download', { timeout: 2000 }).catch(()=>null);
                     await cont.click();
                     dl = await dp;
                 }
             }
             if (dl) {
                 await dl.saveAs('/home/jasondel/dev/coach/' + dl.suggestedFilename());
             }
         }
         // Close files modal by clicking outside
         await page.mouse.click(10, 10);
         await page.waitForTimeout(300);
     }
     
     const exportIcon = page.locator('.downloadIconContainer').first();
     if (await exportIcon.count() > 0) {
         await exportIcon.click();
         await page.waitForTimeout(500);
         const zwo = page.locator('button:has-text("ZWO")').first();
         if (await zwo.count() > 0) {
             let dp = page.waitForEvent('download', { timeout: 2000 }).catch(()=>null);
             await zwo.click();
             let dl = await dp;
             if (dl) {
                 await dl.saveAs('/home/jasondel/dev/coach/planned_workouts/' + dl.suggestedFilename());
             }
         }
     }
     
     const closeBtn = page.getByRole('button', { name: 'Save & Close' });
     if (await closeBtn.count() > 0) {
         await closeBtn.first().click({force:true});
     } else {
         await page.mouse.click(10, 10);
     }
     await page.waitForTimeout(500);
     
     processed.push(id);
     fs.writeFileSync(path, JSON.stringify(processed));
     
     count++;
     if (count >= 35) break; 
  }
  return `Processed ${count} activities. Total processed: ${processed.length}`;
};
