const fs = require('fs');
const path = require('path');

const dbPath = path.join(process.env.APPDATA, 'Code', 'User', 'globalStorage', 'state.vscdb');
const buf = fs.readFileSync(dbPath);
const str = buf.toString('utf-8');

// Search for saoudrizwan keys (Cline's extension ID)
const pat = 'saoudrizwan';
let idx = 0;
let count = 0;
while ((idx = str.indexOf(pat, idx)) !== -1 && count < 20) {
  const start = Math.max(0, idx - 20);
  const end = Math.min(str.length, idx + 400);
  const context = str.substring(start, end).replace(/[^\x20-\x7E]/g, '?');
  console.log(`\n=== Match ${count+1} at offset ${idx} ===`);
  console.log(context);
  idx += pat.length;
  count++;
}
console.log(`\nTotal matches: ${count}`);