const fs = require('fs');
const path = require('path');

// Read the SQLite database as binary and search for Cline API config
const dbPath = path.join(process.env.APPDATA, 'Code', 'User', 'globalStorage', 'state.vscdb');
const buf = fs.readFileSync(dbPath);
const str = buf.toString('utf-8');

// Search for API-related Cline keys
const patterns = ['apiProvider', 'openAiBaseUrl', 'openAiModelId', 'openAiApiKey', 'clineConfig', 'mimo'];
for (const pat of patterns) {
  let idx = 0;
  while ((idx = str.indexOf(pat, idx)) !== -1) {
    const start = Math.max(0, idx - 50);
    const end = Math.min(str.length, idx + 200);
    const context = str.substring(start, end).replace(/[^\x20-\x7E]/g, '?');
    console.log(`\n=== Found "${pat}" at offset ${idx} ===`);
    console.log(context);
    idx += pat.length;
  }
}