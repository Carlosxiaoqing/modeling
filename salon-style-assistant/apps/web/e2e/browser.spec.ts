import { test, expect } from '@playwright/test';
import path from 'node:path';
import { readFileSync } from 'node:fs';
import { unzipSync } from 'fflate';

test('browser-only photos → review → protected presentation → ZIP download', async ({ page }, testInfo) => {
  const errors: string[] = [];
  const requests: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => requests.push(new URL(r.url()).pathname));
  await page.goto('/');
  await page.getByRole('button', { name: '进入工作室', exact: true }).click();
  await page.getByRole('heading', { name: '选择顾客照片', exact: true }).waitFor();
  await page.getByLabel('生成方式').selectOption('demo');
  await page.getByLabel('已向顾客说明并获得本次照片处理授权').check();
  const photo = path.resolve('../../tests/fixtures/synthetic-reference.png');
  await page.getByLabel('正面照片', { exact: true }).setInputFiles(photo);
  await expect(page.getByAltText('正面参考照片')).toBeVisible();
  await page.getByLabel('左侧面照片', { exact: true }).setInputFiles(photo);
  await expect(page.getByAltText('左侧面参考照片')).toBeVisible();
  await page.getByRole('button', { name: '检查照片并继续', exact: true }).click();
  for (const zone of ['刘海', '顶部', '两侧', '后区']) await page.getByLabel(zone + '长度', { exact: true }).selectOption('12-20');
  for (const option of ['可明显改变', '可改变', '不需要', '5～15 分钟', '不接受', '不限制']) await page.getByRole('button', { name: option, exact: true }).click();
  await page.getByRole('button', { name: '确认条件并生成', exact: true }).click();
  await expect(page.getByRole('button', { name: '查看原图与方案', exact: true })).toHaveCount(6);
  await expect(page.getByRole('button', { name: '调整条件或重做', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  for (let i = 0; i < 6; i++) {
    await page.getByRole('button', { name: '查看原图与方案', exact: true }).nth(i).click();
    await page.getByRole('button', { name: '已查看，返回审核', exact: true }).click();
    await page.getByRole('button', { name: '审核通过', exact: true }).nth(i).click();
    await expect(page.locator('.style-card.approved')).toHaveCount(i+1);
  }
  await page.screenshot({ path: testInfo.outputPath('browser-review.png'), fullPage: true });
  await page.getByRole('button', { name: '准备保存', exact: true }).click();
  await page.getByRole('button', { name: '进入展示与下载', exact: true }).click();
  await expect(page.getByRole('button', { name: '保存这张图片', exact: true })).toHaveCount(6);
  expect((await page.request.get('/api/v1/me')).status()).toBe(401);
  const pending = page.waitForEvent('download');
  await page.getByRole('button', { name: '打包下载已审核图片', exact: true }).click();
  const download = await pending;
  const output = testInfo.outputPath('approved.zip'); await download.saveAs(output);
  const files = unzipSync(new Uint8Array(readFileSync(output)));
  expect(Object.keys(files)).toHaveLength(6);
  expect(Object.values(files).every(bytes => bytes[0] === 0xff && bytes[1] === 0xd8)).toBeTruthy();
  expect(requests.some(p => p.includes('/assets/') && p.includes('/api/'))).toBeFalsy();
  expect(requests.some(p => p.includes('uploads') || p.includes('/photos') || p.includes('generation-jobs'))).toBeFalsy();
  expect(await page.evaluate(() => Object.keys(localStorage).length)).toBe(0);
  await page.screenshot({ path: testInfo.outputPath('browser-download.png'), fullPage: true });
  page.on('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: '保存后结束咨询', exact: true }).click();
  await expect(page.getByRole('button', { name: '进入工作室', exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test('refresh drops selected photos and browser persistence remains empty', async ({page})=>{
  await page.goto('/');
  await page.getByRole('button',{name:'进入工作室',exact:true}).click();
  await page.getByLabel('已向顾客说明并获得本次照片处理授权').check();
  await page.getByLabel('正面照片',{exact:true}).setInputFiles(path.resolve('../../tests/fixtures/synthetic-reference.png'));
  await expect(page.getByAltText('正面参考照片')).toBeVisible();
  page.on('dialog',dialog=>dialog.accept());
  await page.reload();
  await page.getByRole('heading',{name:'选择顾客照片',exact:true}).waitFor();
  await expect(page.getByAltText('正面参考照片')).toHaveCount(0);
  expect(await page.evaluate(()=>localStorage.length)).toBe(0);
  expect(await page.evaluate(()=>sessionStorage.length)).toBe(0);
  expect(await page.evaluate(async()=> (await indexedDB.databases()).length)).toBe(0);
});
