const https = require('https');

const options = {
  hostname: 'token-plan-sgp.xiaomimimo.com',
  port: 443,
  path: '/v1/chat/completions',
  method: 'POST',
  headers: {
    'Authorization': 'Bearer tp-svf9i440f463x5kzorbkymjdt0s7fm60ew34belv2tng58i7',
    'Content-Type': 'application/json',
  }
};

const body = JSON.stringify({
  model: 'mimo-v2-omni',
  messages: [{ role: 'user', content: 'say hi' }],
  max_tokens: 10
});

const req = https.request(options, (res) => {
  let data = '';
  res.on('data', (chunk) => data += chunk);
  res.on('end', () => {
    console.log('Status:', res.statusCode);
    console.log('Response:', data.substring(0, 500));
  });
});

req.on('error', (e) => console.error('Error:', e.message));
req.write(body);
req.end();