// Cloudflare Worker to proxy Polymarket CLOB API requests
// Deploy this to Cloudflare Workers (free tier: 100k requests/day)
// Then set CLOB_PROXY=https://your-worker.your-subdomain.workers.dev in Railway

export default {
  async fetch(request, env) {
    // Only allow POST/GET requests
    const url = new URL(request.url);
    
    // Build the target URL
    const targetUrl = `https://clob.polymarket.com${url.pathname}${url.search}`;
    
    // Forward the request with all headers
    const headers = new Headers(request.headers);
    headers.delete('host');
    
    try {
      const response = await fetch(targetUrl, {
        method: request.method,
        headers: headers,
        body: request.method !== 'GET' ? await request.arrayBuffer() : undefined,
      });
      
      // Return the response with CORS headers
      const responseHeaders = new Headers(response.headers);
      responseHeaders.set('Access-Control-Allow-Origin', '*');
      
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });
    } catch (error) {
      return new Response(JSON.stringify({ error: error.message }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      });
    }
  },
};