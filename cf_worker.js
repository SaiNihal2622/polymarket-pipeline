// Cloudflare Worker - Reverse proxy for Polymarket CLOB API
// Bypasses geoblocking since Cloudflare edge IPs aren't blocked
//
// DEPLOYMENT:
// 1. Go to https://dash.cloudflare.com/
// 2. Sign up (free)
// 3. Click "Workers & Pages" → "Create Application" → "Create Worker"
// 4. Name it "poly-clob-proxy" → Deploy
// 5. Click "Edit Code" → Replace all code with this file → Deploy
// 6. Copy the URL (e.g. https://poly-clob-proxy.yourname.workers.dev)
// 7. Set Railway env: railway variables --set CLOB_HOST=<your worker URL>

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const target = "https://clob.polymarket.com" + url.pathname + url.search;
    
    const headers = new Headers(request.headers);
    headers.delete("host");
    headers.set("User-Agent", "Mozilla/5.0");
    
    const init = {
      method: request.method,
      headers,
    };
    
    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = await request.arrayBuffer();
    }
    
    const resp = await fetch(target, init);
    const respHeaders = new Headers(resp.headers);
    respHeaders.set("Access-Control-Allow-Origin", "*");
    
    return new Response(resp.body, {
      status: resp.status,
      headers: respHeaders,
    });
  }
};