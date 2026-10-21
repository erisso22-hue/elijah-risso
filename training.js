/* Training calculations are shared by the browser and Node tests. Weights use kg internally. */
(function(root){
const muscles=['Chest','Back','Shoulders','Biceps','Triceps','Quads','Hamstrings','Glutes','Calves','Core'];
const exercises=[
 ['Bench press',{Chest:1,Shoulders:.5,Triceps:.5}],['Incline bench press',{Chest:1,Shoulders:.5,Triceps:.5}],['Push-up',{Chest:1,Shoulders:.5,Triceps:.5}],
 ['Squat',{Quads:1,Glutes:1,Core:.5}],['Deadlift',{Hamstrings:1,Glutes:1,Back:.5,Core:.5}],['Romanian deadlift',{Hamstrings:1,Glutes:1,Back:.5}],
 ['Overhead press',{Shoulders:1,Triceps:.5,Core:.5}],['Barbell row',{Back:1,Biceps:.5,Shoulders:.5}],['Dumbbell row',{Back:1,Biceps:.5}],
 ['Pull-up',{Back:1,Biceps:.5}],['Lat pulldown',{Back:1,Biceps:.5}],['Leg press',{Quads:1,Glutes:.5}],['Lunge',{Quads:1,Glutes:1,Hamstrings:.5}],
 ['Leg curl',{Hamstrings:1}],['Leg extension',{Quads:1}],['Hip thrust',{Glutes:1,Hamstrings:.5}],['Calf raise',{Calves:1}],['Biceps curl',{Biceps:1}],
 ['Triceps extension',{Triceps:1}],['Lateral raise',{Shoulders:1}],['Crunch',{Core:1}]
];
const canonical=name=>String(name||'').trim().replace(/\s+/g,' ').toLowerCase();
function mapping(entry){if(entry.muscles && typeof entry.muscles==='object')return entry.muscles;const name=canonical(entry.name).replace(/^barbell /,'');return (exercises.find(([n])=>canonical(n)===name)||[])[1]||{}}
function sets(entry){if(Array.isArray(entry.setDetails))return entry.setDetails;return Array.from({length:Math.min(100,Math.max(0,Number(entry.sets)||0))},()=>({reps:Number(entry.reps)||0,weightKg:Number(entry.weight)||0,warmup:false}))}
function volume(entry){return sets(entry).reduce((sum,s)=>sum+s.reps*s.weightKg,0)}
const dayNumber=day=>Date.parse(day+'T00:00:00Z')/86400000;
function progress(logs,name,through){const grouped=new Map();for(const entry of logs){if(entry.type!=='lift'||canonical(entry.name)!==canonical(name)||entry.day>through)continue;const work=sets(entry).filter(s=>!s.warmup);if(!work.length)continue;let day=grouped.get(entry.day);if(!day){day={day:entry.day,sets:0,volume:0,bestWeight:0,bestReps:0,e1rm:null};grouped.set(entry.day,day)}for(const s of work){day.sets++;day.volume+=s.weightKg*s.reps;if(s.weightKg>day.bestWeight||(s.weightKg===day.bestWeight&&s.reps>day.bestReps)){day.bestWeight=s.weightKg;day.bestReps=s.reps}if(s.weightKg>0&&s.reps>=1&&s.reps<=12){const estimate=s.reps===1?s.weightKg:s.weightKg*(1+s.reps/30);day.e1rm=Math.max(day.e1rm||0,estimate)}}}return [...grouped.values()].sort((a,b)=>a.day.localeCompare(b.day))}
function readiness(logs,day,checkin={}){return muscles.map(muscle=>{let debt=0,recentSets=0,last=null;for(const entry of logs){if(entry.type!=='lift')continue;const age=dayNumber(day)-dayNumber(entry.day),load=Number(mapping(entry)[muscle])||0;if(age<0||age>=7||!load)continue;const count=sets(entry).filter(s=>!s.warmup).length;if(!count)continue;recentSets+=count*load;debt+=count*load*12*Math.max(0,1-age/3);if(!last||entry.day>last)last=entry.day}const soreness=Number(checkin.soreness?.[muscle])||0,fatigue=Number(checkin.fatigue)||0;const score=Math.max(0,Math.round(100-Math.min(100,debt)-soreness*15-fatigue*10));return {muscle,score:soreness===3?0:score,recentSets,last,status:soreness===3?'Avoid loading':!last?(soreness>0?'Soreness reported':'No recent data'):score>=75?'More rested':score>=45?'Recovering':'Rest suggested'}}).sort((a,b)=>{if(a.status==='No recent data')return b.status==='No recent data'?0:1;if(b.status==='No recent data')return -1;return b.score-a.score})}
const api={muscles,exercises,canonical,mapping,sets,volume,progress,readiness};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.Training=api;
})(globalThis);
