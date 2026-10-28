import assert from 'node:assert/strict';
import test from 'node:test';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {pinnedPiSource} from './test-environment.mjs';
import {slashCompletions} from '../../../apps/agent/tools/commands.mjs';
import {createCommandCompletionProvider} from '../../../apps/agent/terminal/completion.mjs';

const source=pinnedPiSource();
const {Editor,CombinedAutocompleteProvider,visibleWidth}=await import(pathToFileURL(join(source,'packages/tui/src/index.ts')));
const themes=await import(pathToFileURL(join(source,'packages/coding-agent/src/modes/interactive/theme/theme.ts')));
const settle=async()=>{for(let i=0;i<4;i++) await new Promise(resolve=>setImmediate(resolve));};

function editor() {
  themes.initTheme('dark');
  const input=new Editor({terminal:{rows:24,columns:100},requestRender(){}},themes.getEditorTheme());
  input.setAutocompleteProvider(createCommandCompletionProvider(CombinedAutocompleteProvider,[
    {name:'monitor',description:'Inspect tasks',getArgumentCompletions:prefix=>slashCompletions('monitor',prefix)},
    {name:'model',description:'Select a model'},
    {name:'usage',description:'Inspect usage'},
  ],process.cwd()));
  return input;
}

test('public Editor completion accepts Tab and clicks without submitting',async()=>{
  const input=editor(); let submitted=0;input.onSubmit=()=>submitted++;
  input.handleInput('/');await settle();
  assert.ok(input.render(80).some(line=>line.includes("Select a model")));
  input.handleInput('mo');await settle();
  assert.ok(input.render(80).some(line=>line.includes("Inspect tasks")));
  input.handleInput('\t');
  assert.match(input.getText(),/^\/(monitor|model) /);
  assert.equal(submitted,0);
  input.setText('');input.handleInput('/us');await settle();
  const y=input.render(80).findIndex(line=>line.includes('Inspect usage'));
  assert.ok(y>=0);
  input.handleMouse({type:'press',button:'left',x:1,y,width:80,height:8});
  input.handleMouse({type:'click',button:'left',x:1,y,width:80,height:8});
  assert.equal(input.getText(),'/usage ');assert.equal(submitted,0);
});

test('Tab reopens argument completion after dismissal and preserves task identity',async()=>{
  const input=editor();let submitted=0;input.onSubmit=()=>submitted++;
  input.handleInput('/monitor task ');await settle();
  assert.ok(input.isShowingAutocomplete());
  input.handleInput('\x1b');
  assert.equal(input.getText(),'/monitor task ');
  assert.equal(input.isShowingAutocomplete(),false);
  input.handleInput('\t');await settle();
  assert.ok(input.isShowingAutocomplete());
  input.handleInput('\t');
  assert.equal(input.getText(),'/monitor task pause ');assert.equal(submitted,0);
  input.setText('');input.handleInput('/monitor task cancel TaskABC --k');await settle();
  input.handleInput('\t');
  assert.equal(input.getText(),'/monitor task cancel TaskABC --keep-jobs ');
  assert.equal(submitted,0);
});

test('completion respects terminal widths and bracketed paste does not execute',async()=>{
  const input=editor();let submitted=0;input.onSubmit=()=>submitted++;
  input.handleInput('/');await settle();
  for(const [width,height] of [[100,8],[32,5],[20,4]]) {
    input.setAutocompleteMaxVisible(Math.max(1,height-3));
    const lines=input.render(width);
    assert.ok(lines.length<=height+2);
    for(const line of lines) assert.ok(visibleWidth(line)<=width);
  }
  input.setText('');input.handleInput('\x1b[200~/monitor task pause\nThis is pasted text\x1b[201~');
  assert.equal(submitted,0);
  assert.match(input.getText(),/This is pasted text/);
});
