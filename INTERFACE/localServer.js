// The operator APIs (/api/admin, /api/agents) exist only on the local server, which binds
// to localhost. The public site has none, so it should not ask: every probe there is a
// 404 in the reader's console.
export function onLocalServer(location = globalThis.location) {
  return ['localhost', '127.0.0.1', '[::1]', '::1'].includes(location?.hostname);
}
