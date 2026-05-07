const fs = require('fs');
const path = require('path');

const dbPath = path.join(process.env.APPDATA, 'Code', 'User', 'globalStorage', 'state.vscdb');
const buf = fs.readFileSync(dbPath);
const str = buf.toString('utf-8');

// Search for Cline's actual config keys
const patterns = ['apiProvider', 'openAiBaseUrl', 'openAiModelId', 'openAiApiKey', 'openrouter', 'clineConfig', 'apiModelId', 'modelId', 'baseUrl', 'apiKey'];
for (const pat of patterns) {
  let idx = 0;
  let count = 0;
  while ((idx = str.indexOf(pat, idx)) !== -1 && count < 3) {
    const start = Math.max(0, idx - 80);
    const end = Math.min(str.length, idx + 300);
    const context = str.substring(start, end).replace(/[^\x20-\x7E]/g, '?');
    console.log(`\n=== Found "${pat}" at offset ${idx} ===`);
    console.log(context);
    idx += pat.length;
    count++;
  }
  if (count === 0) console.log(`"${pat}" NOT FOUND`);
}