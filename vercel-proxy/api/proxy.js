// Vercel Serverless Function — CLOB Proxy
// Runs in Mumbai (bom1) to bypass Polymarket geoblocking
export const config = { 
  runtime: 'nodejs',
  regions: ['bom1'],
};

export default async function handler(request, response) {
  const url = new URL(request.url, 'https://clob.polymarket.com');
  let path = url.pathname;
  if (path.startsWith('/api/proxy')) {
    path = path.replace('/api/proxy', '') || '/';
  }
  
  const target = 'https://clob.polymarket.com' + path + url.search;
  
  // Build clean headers
  const headers = {};
  for (const [key, value] of Object.entries(request.headers)) {
    const lower = key.toLowerCase();
    if (['host', 'x-forwarded-for', 'x-real-ip', 'x-forwarded-host',
         'x-forwarded-proto', 'forwarded', 'cf-connecting-ip', 'cf-ray',
         'cf-ipcountry', 'x-vercel-forwarded-for', 'x-vercel-ip-country',
         'x-vercel-id', 'true-client-ip', 'connection'].includes(lower)) continue;
    headers[lower] = value;
  }
  headers['user-agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)';
  // Remove accept-encoding to get plain text response
  delete headers['accept-encoding'];
  
  const fetchOptions = { method: request.method, headers };
  
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    fetchOptions.body = Buffer.concat(chunks);
  }
  
  try {
    const resp = await fetch(target, fetchOptions);
    const body = Buffer.from(await resp.arrayBuffer());
    
    response.status(resp.status);
    for (const [key, value] of resp.headers.entries()) {
      const k = key.toLowerCase();
      // Skip transport headers — Node fetch auto-decompresses
      if (k === 'content-encoding' || k === 'transfer-encoding' || k === 'content-length') continue;
      response.setHeader(key, value);
    }
    response.setHeader('content-length', body.length);
    response.send(body);
  } catch (e) {
    response.status(500).json({ error: e.message });
  }
}