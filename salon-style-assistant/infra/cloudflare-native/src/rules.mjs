export const zones=['fringe','top','sides','back'];
export const lengths={'unknown':null,'0-1':[0,1],'1-3':[1,3],'3-5':[3,5],'5-8':[5,8],'8-12':[8,12],'12-20':[12,20],'20+':[20,null]};
export const dimensions=['visual_balance','feasibility','preference_match','maintenance_match','transition_ease'];
export function score(values,mode){if(dimensions.some(k=>values[k]==null))return null;const v=dimensions.map(k=>values[k]);if(v.some(n=>typeof n!=='number'||!Number.isFinite(n)||n<0||n>5))throw new Error('SCHEMA_INVALID');return Math.round(v.reduce((s,n,i)=>s+n/5*(mode==='current'?[30,30,20,15,5]:[35,20,20,15,10])[i],0));}
export function growth(profile,targets){const bounds=[];for(const[z,t]of Object.entries(targets)){const v=lengths[profile.lengths[z]];if(!v||v[1]==null)return {month_min:null,month_max:null,reason:'请补充可靠长度测量'};bounds.push([Math.max(0,t-v[1])/1.2,Math.max(0,t-v[0])/.8]);}return {month_min:Math.floor(Math.max(0,...bounds.map(b=>b[0]))),month_max:Math.ceil(Math.max(0,...bounds.map(b=>b[1]))),reason:'按每月 0.8～1.2 cm 估算，未计修剪和断发，不是个人生长承诺'};}
export function issues(profile,plan,mode){const out=[];
 if(plan.required_services.includes('perm')&&(profile.perm_acceptance!=='接受'||profile.damage_observation!=='无明显问题'||profile.treatment_history.includes('不确定')))out.push('烫发条件未确认');
 if(profile.tie_back_need==='必须'&&!plan.tie_back_supported)out.push('必须满足扎发');
 if(profile.fringe_preference==='不要刘海'&&!['无刘海','露额'].includes(plan.fringe))out.push('顾客不要刘海');
 if(plan.minimum_density==='中等'&&['偏少','不确定'].includes(profile.density))out.push('密度条件未满足');
 if(mode==='current')for(const[z,t]of Object.entries(plan.minimum_lengths)){const l=lengths[profile.lengths[z]];if(!l||l[0]<t)out.push('长度条件未满足');}
 if(mode==='grow_out'){const cap={'3 个月内':3,'半年内':6,'一年内':12}[profile.waiting_horizon],g=growth(profile,plan.minimum_lengths);if(cap&&g.month_max!=null&&g.month_max>cap)out.push('超出等待期限');}
 return out;
}
export function planValid(p){return p&&['name','family','fringe','parting','texture','description','reason','maintenance'].every(k=>typeof p[k]==='string'&&p[k].length>0&&p[k].length<=1500)&&p.minimum_lengths&&zones.every(z=>Number.isFinite(p.minimum_lengths[z])&&p.minimum_lengths[z]>=0&&p.minimum_lengths[z]<=100)&&Array.isArray(p.required_services)&&p.required_services.every(s=>['cut','perm'].includes(s))&&typeof p.tie_back_supported==='boolean'&&['不限制','中等'].includes(p.minimum_density);}
export function filtered(plans,profile,mode){const seen=new Set();return plans.filter(p=>{if(!planValid(p))return false;const key=[p.family,p.fringe,p.parting,p.texture].join('|');if(seen.has(key)||issues(profile,p,mode).length)return false;seen.add(key);return true;}).slice(0,3);}
export function demoPlans(){return [
 ['轻盈短碎','short_crop','轻薄刘海','自然分缝','碎发纹理',[1,3,1,1],false],['利落侧分','side_part','侧扫刘海','侧分','顺直线条',[3,3,1,1],false],['自然层次','layered','空气刘海','中分','柔和层次',[3,3,3,3],false],['耳际短鲍勃','bob','无刘海','偏分','整齐轮廓',[5,8,5,5],false],['锁骨层次','lob','八字刘海','中分','轻盈层次',[8,12,12,12],true],['长发柔线','long_layered','长刘海','侧分','自然直发',[8,12,12,12],true],['露额短发','crop_open','露额','自然分缝','贴合纹理',[1,1,1,1],false],['长层次中分','long_center','长刘海','中分','纵向层次',[8,12,12,12],true]
 ].map(([name,family,fringe,parting,texture,ls,tie])=>({name,family,fringe,parting,texture,minimum_lengths:Object.fromEntries(zones.map((z,i)=>[z,ls[i]])),tie_back_supported:tie,required_services:[],minimum_density:'不限制',description:[fringe,parting,texture].join(' · '),reason:'演示用结构示例，不代表适合顾客。',maintenance:'维护要求需发型师确认'}));}
