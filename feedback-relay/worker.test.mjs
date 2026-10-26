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
  const response = await worker.fetch(new Request('https://example.com/feedback',{method:'POST'}), {INVITE_CODE:'invitation', GITHUB_TOKEN:'server-only', RATE_LIMITER:{limit:async()=>({success:true})}});
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
