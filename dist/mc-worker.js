// A real Python engine runs off the UI thread. No JavaScript simulation substitute.
let ready;
async function runtime(){
  if(!ready)ready=(async()=>{
    const base='https://cdn.jsdelivr.net/pyodide/v0.28.3/full/';
    postMessage({type:'progress',message:'Loading Python runtime. The first run downloads Python, NumPy and SciPy.'});
    importScripts(base+'pyodide.js');
    const py=await loadPyodide({indexURL:base});
    await py.loadPackage(['numpy','scipy']);
    for(const name of ['mc_core.py','monte_carlo.py']){
      const response=await fetch(name);if(!response.ok)throw Error('Cannot load '+name);
      py.FS.writeFile('/home/pyodide/'+name,await response.text());
    }
    py.runPython('import sys\nsys.path.insert(0, "/home/pyodide")\nfrom monte_carlo import run\nimport json');
    return py;
  })().catch(e=>{ready=null;throw e;});
  return ready;
}
onmessage=async({data})=>{
  try{
    const py=await runtime();postMessage({type:'progress',message:'Sampling supplier disruptions and calculating economic outcomes…'});
    py.globals.set('configuration_json',JSON.stringify(data));
    const result=await py.runPythonAsync('json.dumps(run(json.loads(configuration_json)), allow_nan=False)');
    postMessage({type:'result',result:JSON.parse(result)});
  }catch(error){postMessage({type:'error',message:error.message||String(error)});}
};
