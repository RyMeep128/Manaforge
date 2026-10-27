const reply = (status, body) => Response.json(body, {status, headers: {'Cache-Control': 'no-store'}});
export function validate(p) {
  if (!p || !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(p.id)) return false;
  if (!['Report a Bug', 'Suggest a Feature', 'General Feedback'].includes(p.category)) return false;
  const limits = {title:120, description:12000, steps:8000, behavior:8000, contact:250, operation:500, diagnostics:50000, screenshot:466668};
  if (Object.keys(p).some(k => !['id', 'category', 'metadata', ...Object.keys(limits)].includes(k))) return false;
  for (const [k, max] of Object.entries(limits)) if (typeof p[k] !== 'string' || p[k].length > max) return false;
  if (!p.title.trim() || !p.description.trim()) return false;
  if (!p.metadata || !/^\d+\.\d+\.\d+-(alpha|beta)\.\d+$/.test(p.metadata.version)) return false;
  if (Object.keys(p.metadata).some(k => !['version','os','architecture','python'].includes(k))) return false;
  if (Object.values(p.metadata).some(v => typeof v !== 'string' || v.length > 100)) return false;
  if (p.screenshot) {
    if (!/^[A-Za-z0-9+/]+={0,2}$/.test(p.screenshot)) return false;
    try {
      const bytes = atob(p.screenshot);
      if (bytes.length > 350000 || !(bytes.startsWith('\x89PNG\r\n\x1a\n') || bytes.startsWith('\xff\xd8\xff'))) return false;
    } catch { return false; }
  }
  return true;
}
export default {
  async fetch(request, env) {
    if (new URL(request.url).pathname !== '/feedback' || request.method !== 'POST') return reply(404, {error:'Not found'});
    if (!env.INVITE_CODE || !env.GITHUB_TOKEN) return reply(503, {error:'Not configured'});
    if (!(await env.RATE_LIMITER.limit({key: request.headers.get('CF-Connecting-IP') || 'unknown'})).success) return reply(429, {error:'Try again later'});
    if (request.headers.get('X-Feedback-Invite') !== env.INVITE_CODE) return reply(403, {error:'Invitation required'});
    if (!request.headers.get('Content-Type')?.startsWith('application/json')) return reply(415, {error:'JSON required'});
    let p;
    try {
      const reader = request.body.getReader(); let size = 0; const parts = [];
      while (true) {
        const {value, done} = await reader.read(); if (done) break;
        size += value.length;
        if (size > 600000) { await reader.cancel(); return reply(413, {error:'Too large'}); }
        parts.push(value);
      }
      const bytes = new Uint8Array(size); let offset = 0;
      for (const part of parts) { bytes.set(part, offset); offset += part.length; }
      p = JSON.parse(new TextDecoder().decode(bytes));
    } catch { return reply(400, {error:'Invalid JSON'}); }
    if (!validate(p)) return reply(400, {error:'Invalid report'});
    try {
      // D1 primary key is the global reservation, including concurrent retries.
      const reserved = await env.REPORTS.prepare('INSERT OR IGNORE INTO reports (id,payload) VALUES (?,?)').bind(p.id, JSON.stringify(p)).run();
      if (!reserved.meta.changes) {
        const previous = await env.REPORTS.prepare('SELECT reference FROM reports WHERE id=?').bind(p.id).first();
        return previous?.reference ? reply(200, {id:p.id, reference:previous.reference}) : reply(409, {error:'Report retained; maintainer reconciliation required', id:p.id});
      }
      const label = p.category === 'Report a Bug' ? 'bug' : p.category === 'Suggest a Feature' ? 'enhancement' : 'user-feedback';
      // No user-controlled prose, contact information or attachment reaches GitHub.
      const response = await fetch(`https://api.github.com/repos/${env.GITHUB_REPOSITORY}/issues`, {
        method:'POST', headers:{Authorization:`Bearer ${env.GITHUB_TOKEN}`, Accept:'application/vnd.github+json', 'User-Agent':'Manaforge-feedback', 'X-GitHub-Api-Version':'2022-11-28'},
        body:JSON.stringify({title:`[Friend testing] ${p.category} (${p.metadata.version})`,
          body:`Private feedback reference: ${p.id}\nVersion: ${p.metadata.version}\nCategory: ${p.category}\n\nMaintainer: retrieve report from private feedback storage.`,
          labels:[...new Set([label,'user-feedback','friend-testing',...(p.diagnostics ? ['diagnostics'] : [])])]})});
      if (!response.ok) return reply(503, {error:'Report retained; maintainer reconciliation required', id:p.id});
      const issue = await response.json();
      const reference = String(issue.number);
      await env.REPORTS.prepare("UPDATE reports SET state='submitted', reference=? WHERE id=?").bind(reference,p.id).run();
      return reply(201, {id:p.id, reference});
    } catch { return reply(503, {error:'Not confirmed; retry with the same reference'}); }
  }
};
