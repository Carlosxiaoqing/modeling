import { defineConfig } from '@playwright/test';
import base from './playwright.config';
export default defineConfig({ ...base, testMatch: '**/browser.spec.ts', use: { ...base.use, baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:8791', acceptDownloads: true } });
