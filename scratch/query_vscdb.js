// VS Code's state.vscdb is a SQLite database
// Let's read it properly using the sqlite3 format
const fs = require('fs');
const path = require('path');

const dbPath = path.join(process.env.APPDATA, 'Code', 'User', 'globalStorage', 'state.vscdb');
const buf = fs.readFileSync(dbPath);

// Search for Cline's globalState key - it's stored as JSON with the extension ID
// The key format in the DB is: extensionId + "#" + keyName
// For Cline's globalState, the key is stored differently

// Let's search for specific Cline config values
const searchTerms = [
  'openAiCompatibleBaseUrl',
  'openAiCompatibleApiKey', 
  'openAiCompatibleModelId',
  'apiProvider',
  'mimo-v2-omni',
  'mimo-v2.5-pro',
  'token-plan-sgp',
  'api.xiaomimimo',
];

for (const term of searchTerms) {
  const termBuf = Buffer.from(term, 'utf-8');
  let idx = 0;
  let count = 0;
  while ((idx = buf.indexOf(termBuf, idx)) !== -1 && count < 3) {
    const start = Math.max(0, idx - 50);
    const end = Math.min(buf.length, idx + 300);
    const context = buf.toString('utf-8', start, end).replace(/[^\x20-\x7E]/g, '?');
    console.log(`\n=== "${term}" match ${count+1} at offset ${idx} ===`);
    console.log(context);
    idx += termBuf.length;
    count++;
  }
  if (count === 0) console.log(`"${term}" NOT FOUND in binary`);
}