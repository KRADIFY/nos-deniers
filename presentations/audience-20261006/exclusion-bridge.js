/* Share only the exclusion preference, never an identifier or browsing history. */
(() => {
 const allowed=new Set(['https://plfss.lexmachine.net']);
 addEventListener('message',event=>{
  if(event.source!==parent||!allowed.has(event.origin)||event.data?.type!=='nos-deniers-audience:request')return;
  let excluded=true,available=false;
  try{excluded=localStorage.getItem('nos-deniers-audience-off')==='1';available=true;}catch{}
  event.source.postMessage({type:'nos-deniers-audience:preference',excluded,available},event.origin);
 });
})();
