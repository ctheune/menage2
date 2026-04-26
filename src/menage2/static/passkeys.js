// WebAuthn/Passkey browser helpers

function _base64urlToBuffer(base64url) {
  const base64 = base64url.replace(/-/g, '+').replace(/_/g, '/');
  const binary = atob(base64);
  const buf = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) buf[i] = binary.charCodeAt(i);
  return buf.buffer;
}

function _bufferToBase64url(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

async function startPasskeyLogin(beginUrl, completeUrl) {
  const beginResp = await fetch(beginUrl, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
  if (!beginResp.ok) throw new Error('Failed to start passkey login.');
  const options = await beginResp.json();

  options.challenge = _base64urlToBuffer(options.challenge);
  if (options.allowCredentials) {
    options.allowCredentials = options.allowCredentials.map(c => ({
      ...c, id: _base64urlToBuffer(c.id)
    }));
  }

  const credential = await navigator.credentials.get({ publicKey: options });

  const body = {
    id: credential.id,
    rawId: _bufferToBase64url(credential.rawId),
    type: credential.type,
    response: {
      authenticatorData: _bufferToBase64url(credential.response.authenticatorData),
      clientDataJSON: _bufferToBase64url(credential.response.clientDataJSON),
      signature: _bufferToBase64url(credential.response.signature),
      userHandle: credential.response.userHandle ? _bufferToBase64url(credential.response.userHandle) : null,
    },
  };

  const completeResp = await fetch(completeUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const result = await completeResp.json();
  if (result.ok) {
    window.location.href = result.redirect || '/';
  } else {
    throw new Error(result.error || 'Passkey authentication failed.');
  }
}

async function startPasskeyRegistration(beginUrl, completeUrl, deviceName) {
  const beginResp = await fetch(beginUrl, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
  if (!beginResp.ok) throw new Error('Failed to start passkey registration.');
  const options = await beginResp.json();

  options.challenge = _base64urlToBuffer(options.challenge);
  options.user.id = _base64urlToBuffer(options.user.id);
  if (options.excludeCredentials) {
    options.excludeCredentials = options.excludeCredentials.map(c => ({
      ...c, id: _base64urlToBuffer(c.id)
    }));
  }

  // Remove authenticatorSelection so browsers don't restrict to platform authenticators,
  // allowing cross-platform providers like 1Password to respond.
  delete options.authenticatorSelection;

  const credential = await navigator.credentials.create({ publicKey: options });

  const body = {
    id: credential.id,
    rawId: _bufferToBase64url(credential.rawId),
    type: credential.type,
    device_name: deviceName,
    response: {
      attestationObject: _bufferToBase64url(credential.response.attestationObject),
      clientDataJSON: _bufferToBase64url(credential.response.clientDataJSON),
    },
  };

  const completeResp = await fetch(completeUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const result = await completeResp.json();
  if (!result.ok) throw new Error(result.error || 'Passkey registration failed.');
}
