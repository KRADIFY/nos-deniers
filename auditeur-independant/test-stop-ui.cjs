const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const nodes=new Map(),calls=[];let response={status:'idle'};
function node(id){if(!nodes.has(id))nodes.set(id,{hidden:false,disabled:false,textContent:'',handlers:{},addEventListener(k,f){this.handlers[k]=f},replaceChildren(){},removeAttribute(){}});return nodes.get(id)}
const c=vm.createContext({Intl,Date,JSON,Error,document:{getElementById:node,querySelector:()=>node('status')},setInterval(){},fetch:async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>response}}});
vm.runInContext(fs.readFileSync(__dirname+'/web/app.js','utf8'),c);
(async()=>{
 await new Promise(setImmediate);assert.equal(node('stop').hidden,true);
 vm.runInContext("show({status:'running',run_id:'20260929-120000-abcdef'})",c);assert.equal(node('stop').hidden,false);assert.equal(node('start').disabled,true);
 response={status:'stopping',run_id:'20260929-120000-abcdef'};await node('stop').handlers.click();assert.equal(calls.at(-1).url,'/api/stop');assert.equal(JSON.parse(calls.at(-1).options.body).run_id,response.run_id);assert.equal(node('stop').disabled,true);
 vm.runInContext("show({status:'interrupted',run_id:'20260929-120000-abcdef'})",c);assert.equal(node('stop').hidden,true);assert.equal(node('resume').hidden,false);assert.equal(node('start').disabled,false);
 console.log('Interface : lancement, arret en cours, cible exacte et reprise verifies.');
})().catch(e=>{console.error(e);process.exitCode=1});
