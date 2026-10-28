import test from 'node:test';
import assert from 'node:assert/strict';
import worker, {validate} from './worker.mjs';
const report = () => ({id:crypto.randomUUID(), category:'Report a Bug', title:'Oops', description:'Help', steps:'', behavior:'', contact:'', diagnostics:'', screenshot:'', operation:'', metadata:{version:'0.3.2-alpha.1',os:'Windows',python:'3.12',architecture:'AMD64'}});
test('bounds and allowlists', () => {
  assert.equal(validate(report()), true);
  assert.equal(validate({...report(), title:'x'.repeat(121)}), false);
  assert.equal(validate({...report(), category:'arbitrary-label'}), false);
  assert.equal(validate({...report(), token:'secret'}), false);
  assert.equal(validate({...report(), screenshot:'not an image'}), false);
});
test('unauthorized requests never reach storage', async () => {
  const response = await worker.fetch(new Request('https://example.com/feedback',{method:'POST'}), {REQUIRE_INVITE:'true', INVITE_CODE:'invitation', GITHUB_TOKEN:'server-only', RATE_LIMITER:{limit:async()=>({success:true})}});
  assert.equal(response.status,403);
});
test('retries return existing reference without GitHub call', async () => {
  const env = {INVITE_CODE:'invitation', GITHUB_TOKEN:'server-only', RATE_LIMITER:{limit:async()=>({success:true})}, REPORTS:{prepare:()=>({bind:()=>({run:async()=>({meta:{changes:0}}),first:async()=>({reference:'17'})})})}};
  const response = await worker.fetch(new Request('https://example.com/feedback',{method:'POST',headers:{'Content-Type':'application/json','X-Feedback-Invite':'invitation'},body:JSON.stringify(report())}),env);
  assert.equal(response.status,200);
  assert.equal((await response.json()).reference,'17');
});
test('rate limited request is rejected before parsing', async () => {
  const response = await worker.fetch(new Request('https://example.com/feedback',{method:'POST'}),{INVITE_CODE:'x',GITHUB_TOKEN:'x',RATE_LIMITER:{limit:async()=>({success:false})}});
  assert.equal(response.status,429);
});


test('decoded screenshot limit matches desktop client', () => {
  const image = Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]), Buffer.alloc(350000 - 8)]);
  assert.equal(validate({...report(), screenshot:image.toString('base64')}), true);
  assert.equal(validate({...report(), screenshot:Buffer.concat([image, Buffer.from([0])]).toString('base64')}), false);
});

test('approved attachments are stored privately and only references reach GitHub', async () => {
  const originalFetch = globalThis.fetch;
  const submitted = {...report(), diagnostics:'sanitized error trace', screenshot:'iVBORw0KGgo='};
  let stored, issue;
  const statements = [];
  const env = {INVITE_CODE:'invitation', GITHUB_TOKEN:'server-only', GITHUB_REPOSITORY:'owner/repo',
    RATE_LIMITER:{limit:async()=>({success:true})},
    REPORTS:{prepare:(sql)=>({bind:(...values)=>({run:async()=>{
      statements.push(sql);
      if (sql.startsWith('INSERT')) stored = JSON.parse(values[1]);
      return {meta:{changes:1}};
    }})})}};
  globalThis.fetch = async (url, options) => {
    issue = JSON.parse(options.body);
    return Response.json({number:42}, {status:201});
  };
  try {
    const response = await worker.fetch(new Request('https://example.com/feedback', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify(submitted)}), env);
    assert.equal(response.status,201);
    assert.deepEqual(await response.json(), {id:submitted.id, reference:'42'});
    assert.deepEqual(stored,submitted);
    assert.equal(JSON.stringify(issue).includes(submitted.diagnostics),false);
    assert.equal(JSON.stringify(issue).includes(submitted.screenshot),false);
    assert.equal(issue.labels.includes('diagnostics'),true);
    assert.equal(statements.some(sql=>sql.startsWith('UPDATE')),true);
  } finally { globalThis.fetch = originalFetch; }
});

test('uncertain previous submission never creates a duplicate issue', async () => {
  const env = {INVITE_CODE:'invitation', GITHUB_TOKEN:'server-only', RATE_LIMITER:{limit:async()=>({success:true})},
    REPORTS:{prepare:()=>({bind:()=>({run:async()=>({meta:{changes:0}}),first:async()=>({reference:null})})})}};
  const response = await worker.fetch(new Request('https://example.com/feedback', {
    method:'POST', headers:{'Content-Type':'application/json','X-Feedback-Invite':'invitation'},
    body:JSON.stringify(report())}), env);
  assert.equal(response.status,409);
});
