const https = require('https');

const options = {
  hostname: 'integrate.api.nvidia.com',
  port: 443,
  path: '/v1/chat/completions',
  method: 'POST',
  headers: {
    'Authorization': 'Bearer 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',
    'Content-Type': 'application/json',
  }
};

const body = JSON.stringify({
  model: 'meta/llama-3.2-90b-vision-instruct',
  messages: [{ role: 'user', content: 'Say hello in one sentence.' }],
  max_tokens: 50
});

const req = https.request(options, (res) => {
  let data = '';
  res.on('data', (chunk) => data += chunk);
  res.on('end', () => {
    console.log('Status:', res.statusCode);
    console.log('Response:', data.substring(0, 800));
  });
});

req.on('error', (e) => console.error('Error:', e.message));
req.write(body);
req.end();