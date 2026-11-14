// Read-only fixed-baseline imports. Writes only the caller's synthetic fixture.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import {performance} from 'node:perf_hooks';
import {initializeStory,importStory,loadStory} from '../.baseline/dist/core/project.js';
import {replaceSegmentPrompt} from '../.baseline/dist/core/prompt-replacement.js';
import {registerAsset} from '../.baseline/dist/assets/registry.js';
import {buildRequest} from '../.baseline/dist/metaso/h3.js';
globalThis.fetch=()=>{throw Error('Offline baseline must not access network');};
const [mode,dir]=process.argv.slice(2),base=resolve(dir),root=join(base,'node-story');
if(mode==='setup'){
 await initializeStory(root,'Synthetic differential');
 for(let e=1;e<=6;e++){
  const count=e<6?2:1,texts=Array.from({length:count},(_,s)=>`第${e}集第${s+1}段😀。\n`);
  const source=join(base,`source-${e}.txt`);await writeFile(source,'\uFEFF'+texts.join('').replaceAll('\n','\r\n'));
  let cursor=0;const segments=texts.map((prompt,s)=>{const start=cursor;cursor+=prompt.length;return {id:`s${s+1}`,start,end:cursor,duration:6.666,references:[{assetId:'hero',role:'reference_image'}]};});
  await importStory(root,{episodeId:`ep-${e}`,kind:'video-prompts',source,segments,recipes:[{assetId:'hero',kind:'character',prompt:'完整人物配方',dependencies:[],exactText:[]}]});
 }
 await registerAsset(root,'hero',{file:join(base,'red.png')});
}else if(mode==='hot'||mode==='hot-image'){
 const times=[];
 for(let i=0;i<20;i++){
  const before=performance.now();
  if(mode==='hot')await replaceSegmentPrompt(root,{episodeId:'ep-1',segmentId:'s1',file:join(base,`replace-${i%2}.txt`)});
  else await registerAsset(root,'hero',{file:join(base,i%2?'red.png':'blue.png')});
  times.push(performance.now()-before);
 }
 console.log(JSON.stringify(times));
}else if(mode==='payload'){
 const story=await loadStory(root),results=[];
 // createPlan's current h3-inline-ir path explicitly overrides the legacy
 // manifest default before buildRequest; compare that actual send policy.
 for(const episode of story.episodes)for(const segment of episode.segments)results.push((await buildRequest(root,story,{...segment,parameters:{...segment.parameters,contextIr:true}})).request);
 console.log(JSON.stringify(results));
}else throw Error('Unknown benchmark mode');
