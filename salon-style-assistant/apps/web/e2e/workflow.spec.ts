import { test, expect } from '@playwright/test';
import path from 'node:path';

test('photo → confirmed profile → six reviewed styles → readonly display → choice', async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('/');
  await page.getByRole('button', { name: '进入工作室', exact: true }).click();
  await page.getByRole('button', { name: '新建咨询', exact: true }).waitFor();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath('dashboard.png'), fullPage: true });
  await page.getByRole('button', { name: '新建咨询', exact: true }).click();
  await page.getByLabel('顾客代号', { exact: true }).fill(`自动测试-${testInfo.project.name}`);
  await page.getByLabel('生成方式', { exact: true }).selectOption('demo');
  await page.getByRole('button', { name: '创建咨询', exact: true }).click();
  await page.getByLabel('已向顾客说明，并获得本次照片处理授权').check();
  const photo = path.resolve('../../tests/fixtures/synthetic-reference.png');
  await page.getByLabel('正面照片', { exact: true }).setInputFiles(photo);
  await expect(page.getByAltText('正面原始参考照片')).toBeVisible();
  await page.getByLabel('左侧面照片', { exact: true }).setInputFiles(photo);
  await expect(page.getByAltText('左侧面原始参考照片')).toBeVisible();
  await page.getByRole('button', { name: '继续确认条件', exact: true }).click();
  for (const zone of ['刘海', '顶部', '两侧', '后区']) await page.getByLabel(zone + '长度', { exact: true }).selectOption('12-20');
  for (const option of ['可明显改变', '可改变', '不需要', '5～15 分钟', '不接受', '不限制']) await page.getByRole('button', { name: option, exact: true }).click();
  await page.getByRole('button', { name: '确认并保存', exact: true }).click();
  await page.getByRole('button', { name: '生成方案', exact: true }).click();
  await expect(page.getByRole('button', { name: '查看结构与原图', exact: true })).toHaveCount(6);
  await page.reload();
  await page.getByRole('button', { name: /自动测试-/ }).first().click();
  await expect(page.getByRole('button', { name: '查看结构与原图', exact: true })).toHaveCount(6);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  for (let i=0;i<6;i++) {
    await page.getByRole('button', { name: '查看结构与原图', exact: true }).nth(i).click();
    await page.getByRole('button', { name: '已查看，返回审核', exact: true }).click();
    await page.getByRole('button', { name: '审核通过', exact: true }).nth(i).click();
    await expect(page.getByText('已审核', { exact: true })).toHaveCount(i+1);
  }
  await page.screenshot({ path: testInfo.outputPath('review.png'), fullPage: true });
  await page.getByRole('button', { name: '准备顾客展示', exact: true }).click();
  await page.getByRole('button', { name: '进入演示展示', exact: true }).click();
  await expect(page.getByRole('button', { name: '我喜欢这一款', exact: true })).toHaveCount(6);
  expect((await page.request.get('/api/v1/me')).status()).toBe(401);
  await page.getByRole('button', { name: '我喜欢这一款', exact: true }).first().click();
  await expect(page.getByRole('button', { name: '已记录喜欢', exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('presentation.png'), fullPage: true });
  await page.getByRole('button', { name: '交回发型师', exact: true }).click();
  await expect(page.getByRole('button', { name: '进入工作室', exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
