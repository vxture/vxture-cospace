// Test-only bridge to Node's native crypto. stdin/stdout JSON; no network or files.
import { createPrivateKey, createPublicKey, sign, verify } from 'node:crypto';
const chunks = [];
let size = 0;
for await (const chunk of process.stdin) {
  size += chunk.length;
  if (size > 131072) throw new Error('probe input limit');
  chunks.push(chunk);
}
const request = JSON.parse(Buffer.concat(chunks).toString('utf8'));
const message = Buffer.from(request.message, 'base64');
if (request.operation === 'sign-test') {
  // RFC 8410 PKCS#8 wrapping of a 32-byte test seed; cryptography is native.
  const seed = Buffer.from(request.seed, 'hex');
  if (seed.length !== 32) throw new Error('test seed length');
  const key = createPrivateKey({ key: Buffer.concat([Buffer.from('302e020100300506032b657004220420', 'hex'), seed]), format: 'der', type: 'pkcs8' });
  const pub = createPublicKey(key).export({ format: 'der', type: 'spki' });
  process.stdout.write(JSON.stringify({ public_key: pub.subarray(-32).toString('hex'), signature: sign(null, message, key).toString('hex') }));
} else if (request.operation === 'verify') {
  const publicKey = Buffer.from(request.public_key, 'hex');
  const signature = Buffer.from(request.signature, 'hex');
  if (publicKey.length !== 32 || signature.length !== 64) throw new Error('key/signature length');
  const key = createPublicKey({ key: Buffer.concat([Buffer.from('302a300506032b6570032100', 'hex'), publicKey]), format: 'der', type: 'spki' });
  process.stdout.write(JSON.stringify({ valid: verify(null, message, key, signature) }));
} else {
  throw new Error('unsupported probe operation');
}
