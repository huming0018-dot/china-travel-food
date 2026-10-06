'use strict';
// Runtime dependencies live in app; pg/Playwright are optional development tools.
const {spawnSync}=require('node:child_process');
const path=require('node:path');
const root=path.resolve(__dirname,'../..');
const commands=[
  [process.execPath,'crowd_extension/tests/check.cjs'],
  [process.execPath,'crowd_extension/tests/worker.cjs'],
  [process.execPath,'crowd_extension/tests/join.cjs'],
  [process.execPath,'crowd_extension/tests/native.cjs'],
  [process.env.PYTHON||'python3','crowd_extension/tests/check_operator.py'],
  [process.env.PYTHON||'python3','crowd_extension/tests/check_launch.py']
];
if(process.env.CROWD_TEST_TOOLS)commands.push([process.execPath,'crowd_extension/tests/browser.mjs']);
if(process.env.CROWD_PORTAL_TEST_ORIGIN) {
  if(!process.env.CROWD_TEST_TOOLS)throw new Error('Portal tests require CROWD_TEST_TOOLS with Playwright');
  commands.push([process.execPath,'crowd_extension/tests/portal.mjs']);
}
for(const [command,...args]of commands){
  const result=spawnSync(command,args,{cwd:root,env:process.env,stdio:'inherit'});
  if(result.error){console.error(result.error.message);process.exit(1);}
  if(result.status!==0)process.exit(result.status||1);
}
console.log('PASS current v4 checks; see individual outputs for database/browser/OS coverage limits');
