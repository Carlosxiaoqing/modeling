import test from 'node:test';import assert from 'node:assert/strict';
import {score,growth,issues,filtered,demoPlans,dimensions} from './src/rules.mjs';
import {stripMetadata,imageInfo} from './src/providers.mjs';
import {readFileSync} from 'node:fs';
test('scores require complete evidence and use independent mode weights',()=>{assert.equal(score(Object.fromEntries(dimensions.map(k=>[k,5])),'current'),100);assert.equal(score({visual_balance:5},'current'),null);assert.throws(()=>score(Object.fromEntries(dimensions.map(k=>[k,6])),'grow_out'));});
test('unknown lengths have no fabricated growth date',()=>{const p={lengths:{top:'unknown'}};assert.equal(growth(p,{top:12}).month_min,null);assert.deepEqual([growth({lengths:{top:'3-5'}},{top:11}).month_min,growth({lengths:{top:'3-5'}},{top:11}).month_max],[5,10]);});
test('length, tie and service constraints survive the native port',()=>{const p={lengths:{top:'unknown'},tie_back_need:'必须',perm_acceptance:'可讨论',treatment_history:['不确定']};assert.ok(issues(p,{required_services:['perm'],minimum_lengths:{top:3},tie_back_supported:false},'current').length>=3);});
test('duplicate plans cannot fill the default group',()=>{const p={lengths:Object.fromEntries(['fringe','top','sides','back'].map(z=>[z,'12-20'])),treatment_history:['无']};assert.equal(filtered([...demoPlans(),...demoPlans()],p,'current').length,3);});
test('photo sniffing and metadata processing reject non-images',()=>{assert.throws(()=>imageInfo(new Uint8Array([1,2,3])));const bytes=new Uint8Array(readFileSync('../../tests/fixtures/synthetic-reference.png'));const out=stripMetadata(bytes);assert.equal(out.width,400);assert.equal(out.height,500);assert.equal(out.mime,'image/png');});
