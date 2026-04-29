/**
 * Cloudflare Worker — Vaillant boiler API proxy.
 * Authenticates directly with Vaillant identity service (PKCE OAuth2)
 * and proxies boost / data-read requests.
 *
 * Environment variables (CF dashboard → Worker → Settings → Variables):
 *   VAILLANT_USERNAME  — myVaillant email
 *   VAILLANT_PASSWORD  — myVaillant password
 *   GITHUB_TOKEN       — fine-grained PAT with contents:write (for CSV commit)
 *
 * Endpoints:
 *   POST /boost      — start DHW cylinder boost
 *   POST /cancel     — cancel DHW boost
 *   POST /data       — read boiler data (+ commit CSV to GitHub)
 *   POST /trigger    — legacy: GitHub repository_dispatch
 *
 * Deploy: cd cloudflare-worker && npx wrangler deploy
 */

// ── Constants ────────────────────────────────────────────────────
const AUTH_BASE    = 'https://identity.vaillant-group.com/auth/realms';
const REALM        = 'vaillant-poland-b2c';
const CLIENT_ID    = 'myvaillant';
const REDIRECT_URI = 'enduservaillant.page.link://login';
const API_BASE     = 'https://api.vaillant-group.com/service-connected-control/end-user-app-api/v1';
const REPO         = 'konradmakosa/vaillant';

const CORS_HEADERS = {
  'Content-Type': 'application/json',
  'Access-Control-Allow-Origin': '*',
};
const AUTH_HEADERS = {
  'x-app-identifier': 'VAILLANT',
  'Accept-Language': 'en-GB',
  'Accept': 'application/json, text/plain, */*',
  'x-client-locale': 'en-GB',
  'x-idm-identifier': 'KEYCLOAK',
  'ocp-apim-subscription-key': '1e0a2f3511fb4c5bbb1c7f9fedd20b1c',
  'User-Agent': 'okhttp/4.9.2',
  'Connection': 'keep-alive',
};

const COOLDOWNS = {
  boost:  60,      // 1 min
  cancel: 60,
  data:   600,     // 10 min
  trigger: 600,
};

// ── Helpers ──────────────────────────────────────────────────────
function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: CORS_HEADERS });
}

function corsPreflightResponse() {
  return new Response(null, {
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    },
  });
}

async function checkCooldown(action) {
  const cache = caches.default;
  const key = `https://vaillant-trigger.internal/cooldown/${action}`;
  const cached = await cache.match(key);
  if (cached) {
    const age = (Date.now() / 1000) - parseFloat(await cached.text());
    if (age < (COOLDOWNS[action] || 60)) {
      return Math.ceil((COOLDOWNS[action] || 60) - age);
    }
  }
  return 0;
}

async function setCooldown(action) {
  const cache = caches.default;
  const key = `https://vaillant-trigger.internal/cooldown/${action}`;
  const resp = new Response(String(Date.now() / 1000), {
    headers: { 'Cache-Control': `max-age=${COOLDOWNS[action] || 60}` },
  });
  await cache.put(key, resp);
}

// ── PKCE helpers ─────────────────────────────────────────────────
function base64url(buffer) {
  const bytes = new Uint8Array(buffer);
  let s = '';
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function randomString(len) {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  const arr = crypto.getRandomValues(new Uint8Array(len));
  return Array.from(arr, b => chars[b % chars.length]).join('');
}

async function generatePKCE() {
  const verifier = randomString(128);
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  const challenge = base64url(digest);
  return { verifier, challenge };
}

// ── Vaillant OAuth2 login ────────────────────────────────────────
async function vaillantLogin(username, password) {
  const { verifier, challenge } = await generatePKCE();

  const authParams = new URLSearchParams({
    response_type: 'code',
    client_id: CLIENT_ID,
    code: 'code_challenge',
    redirect_uri: REDIRECT_URI,
    code_challenge_method: 'S256',
    code_challenge: challenge,
  });

  // Step 1: GET login page to extract form action URL
  const authUrl = `${AUTH_BASE}/${REALM}/protocol/openid-connect/auth?${authParams}`;
  const pageResp = await fetch(authUrl, {
    headers: { 'User-Agent': 'okhttp/4.9.2', 'Accept': 'text/html' },
    redirect: 'manual',
  });

  // Check if we got a direct redirect with code (unlikely but possible)
  let code = null;
  const loc = pageResp.headers.get('Location');
  if (loc) {
    const u = new URL(loc);
    code = u.searchParams.get('code');
  }

  if (!code) {
    // Collect session cookies from step 1 response
    const allSetCookies = pageResp.headers.getAll
      ? pageResp.headers.getAll('Set-Cookie')
      : [pageResp.headers.get('Set-Cookie')].filter(Boolean);
    const cookieHeader = allSetCookies.map(c => c.split(';')[0]).join('; ');

    // Parse login form URL from HTML
    const html = await pageResp.text();
    const loginUrlPattern = `${AUTH_BASE}/${REALM}/login-actions/authenticate`;
    const regex = new RegExp(loginUrlPattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\?[^"]*');
    const match = html.match(regex);
    if (!match) {
      throw new Error('Could not find login form URL in HTML');
    }
    const loginUrl = match[0].replace(/&amp;/g, '&');

    // Step 2: POST credentials with session cookies
    const loginResp = await fetch(loginUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'okhttp/4.9.2',
        'Cookie': cookieHeader,
      },
      body: new URLSearchParams({ username, password, credentialId: '' }),
      redirect: 'manual',
    });

    const redirectUrl = loginResp.headers.get('Location');
    if (!redirectUrl) {
      throw new Error('Login failed — no redirect (wrong credentials?)');
    }
    const rUrl = new URL(redirectUrl);
    code = rUrl.searchParams.get('code');
    if (!code) {
      throw new Error('Login failed — no code in redirect');
    }
  }

  // Step 3: Exchange code for tokens
  const tokenResp = await fetch(`${AUTH_BASE}/${REALM}/protocol/openid-connect/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: CLIENT_ID,
      code,
      code_verifier: verifier,
      redirect_uri: REDIRECT_URI,
    }),
  });

  if (!tokenResp.ok) {
    const txt = await tokenResp.text();
    throw new Error(`Token exchange failed: ${tokenResp.status} ${txt}`);
  }

  return await tokenResp.json();
}

// ── Vaillant API helpers ─────────────────────────────────────────
function apiHeaders(accessToken) {
  return { ...AUTH_HEADERS, Authorization: `Bearer ${accessToken}` };
}

async function getSystemInfo(accessToken) {
  // Get homes
  const homesResp = await fetch(`${API_BASE}/homes`, { headers: apiHeaders(accessToken) });
  if (!homesResp.ok) throw new Error(`homes: ${homesResp.status}`);
  const homes = await homesResp.json();
  if (!homes.length) throw new Error('No homes found');
  const systemId = homes[0].systemId;

  // Get control identifier
  const ciResp = await fetch(
    `${API_BASE}/systems/${systemId}/meta-info/control-identifier`,
    { headers: apiHeaders(accessToken) }
  );
  if (!ciResp.ok) throw new Error(`control-identifier: ${ciResp.status}`);
  const ci = await ciResp.json();
  const controlId = ci.controlIdentifier || 'tli';

  return { systemId, controlId };
}

function systemUrl(systemId, controlId) {
  const suffix = controlId === 'tli' ? '/tli' : '';
  return `${API_BASE}/systems/${systemId}${suffix}`;
}

// ── Actions ──────────────────────────────────────────────────────
async function doBoost(accessToken) {
  const { systemId, controlId } = await getSystemInfo(accessToken);
  const url = `${systemUrl(systemId, controlId)}/domestic-hot-water/255/boost`;
  const resp = await fetch(url, {
    method: 'POST',
    headers: { ...apiHeaders(accessToken), 'Content-Type': 'application/json' },
    body: '{}',
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`Boost failed: ${resp.status} ${txt}`);
  }
  return { status: 'ok', action: 'boost' };
}

async function doCancelBoost(accessToken) {
  const { systemId, controlId } = await getSystemInfo(accessToken);
  const url = `${systemUrl(systemId, controlId)}/domestic-hot-water/255/boost`;
  const resp = await fetch(url, {
    method: 'DELETE',
    headers: apiHeaders(accessToken),
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`Cancel boost failed: ${resp.status} ${txt}`);
  }
  return { status: 'ok', action: 'cancel' };
}

async function doReadData(accessToken, env) {
  const { systemId, controlId } = await getSystemInfo(accessToken);
  const url = systemUrl(systemId, controlId);
  const resp = await fetch(url, { headers: apiHeaders(accessToken) });
  if (!resp.ok) throw new Error(`System read failed: ${resp.status}`);
  const raw = await resp.json();

  // Extract key values
  const sys = raw.state?.system || raw.system || {};
  const zones = raw.state?.zones || raw.zones || [];
  const dhwArr = raw.state?.dhw || raw.dhw || [];
  const circuits = raw.state?.circuits || raw.circuits || [];

  const zone = zones[0] || {};
  const dhw = dhwArr[0] || {};
  const circuit = circuits[0] || {};

  const data = {
    timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
    water_pressure_bar: sys.systemWaterPressure ?? sys.system_water_pressure ?? null,
    outdoor_temp_c: sys.outdoorTemperature ?? sys.outdoor_temperature ?? null,
    circuit_flow_temp_c: circuit.currentCircuitFlowTemperature ?? circuit.current_circuit_flow_temperature ?? null,
    energy_manager_state: sys.energyManagerState ?? sys.energy_manager_state ?? null,
    circuit_state: circuit.circuitState ?? circuit.circuit_state ?? null,
    connected: true,
    zone_name: zone.configuration?.general?.name ?? zone.name ?? null,
    zone_current_temp_c: zone.state?.currentRoomTemperature ?? zone.currentRoomTemperature ?? zone.current_room_temperature ?? null,
    zone_target_temp_c: zone.state?.desiredRoomTemperatureSetpoint ?? zone.desiredRoomTemperatureSetpoint ?? null,
    zone_humidity_pct: zone.state?.currentRoomHumidity ?? zone.currentRoomHumidity ?? null,
    zone_heating_state: zone.state?.heatingState ?? zone.heatingState ?? zone.heating_state ?? null,
    dhw_current_temp_c: dhw.state?.currentDhwTemperature ?? dhw.currentDhwTemperature ?? dhw.current_dhw_temperature ?? null,
    dhw_target_temp_c: dhw.configuration?.tappingSetpoint ?? dhw.tappingSetpoint ?? dhw.tapping_setpoint ?? null,
    dhw_operation_mode: dhw.configuration?.operationModeDhw ?? dhw.operationModeDhw ?? dhw.operation_mode_dhw ?? null,
    dhw_current_special_function: dhw.state?.currentSpecialFunction ?? dhw.currentSpecialFunction ?? dhw.current_special_function ?? null,
  };

  // Commit CSV row to GitHub if GITHUB_TOKEN is set
  if (env.GITHUB_TOKEN) {
    try {
      await commitCsvRow(env.GITHUB_TOKEN, data);
    } catch (e) {
      data._csv_error = e.message;
    }
  }

  return { status: 'ok', action: 'data', data };
}

// ── GitHub CSV commit ────────────────────────────────────────────
async function commitCsvRow(token, data) {
  const now = new Date();
  const month = `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, '0')}`;
  const path = `data/boiler_${month}.csv`;
  const ghHeaders = {
    Authorization: `Bearer ${token}`,
    Accept: 'application/vnd.github+json',
    'User-Agent': 'vaillant-cf-worker',
    'Content-Type': 'application/json',
  };

  const CSV_HEADERS = [
    'timestamp','water_pressure_bar','outdoor_temp_c','circuit_flow_temp_c',
    'energy_manager_state','circuit_state','connected','zone_name',
    'zone_current_temp_c','zone_target_temp_c','zone_humidity_pct','zone_heating_state',
    'dhw_current_temp_c','dhw_target_temp_c','dhw_operation_mode','dhw_current_special_function',
  ];

  // Get existing file (if any)
  let existingContent = '';
  let sha = null;
  const getResp = await fetch(`https://api.github.com/repos/${REPO}/contents/${path}`, {
    headers: ghHeaders,
  });
  if (getResp.ok) {
    const file = await getResp.json();
    sha = file.sha;
    existingContent = atob(file.content.replace(/\n/g, ''));
  }

  // Build new row
  const row = CSV_HEADERS.map(h => {
    const v = data[h];
    return v === null || v === undefined ? '' : String(v);
  }).join(',');

  let newContent;
  if (!existingContent) {
    newContent = CSV_HEADERS.join(',') + '\n' + row + '\n';
  } else {
    // Ensure header is up to date
    const lines = existingContent.split('\n');
    if (lines[0] !== CSV_HEADERS.join(',')) {
      lines[0] = CSV_HEADERS.join(',');
    }
    newContent = lines.join('\n').replace(/\n*$/, '\n') + row + '\n';
  }

  const commitBody = {
    message: `data: ${data.timestamp} UTC`,
    content: btoa(newContent),
  };
  if (sha) commitBody.sha = sha;

  const putResp = await fetch(`https://api.github.com/repos/${REPO}/contents/${path}`, {
    method: 'PUT',
    headers: ghHeaders,
    body: JSON.stringify(commitBody),
  });

  if (!putResp.ok) {
    const txt = await putResp.text();
    throw new Error(`GitHub commit failed: ${putResp.status} ${txt}`);
  }
}

// ── Legacy: GitHub repository_dispatch ───────────────────────────
async function doTrigger(action, env) {
  const token = env.GITHUB_TOKEN;
  if (!token) throw new Error('GITHUB_TOKEN not configured');

  const resp = await fetch(`https://api.github.com/repos/${REPO}/dispatches`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'User-Agent': 'vaillant-cf-worker',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ event_type: action }),
  });

  if (resp.status === 204) return { status: 'triggered', action };
  const body = await resp.text();
  throw new Error(`GitHub dispatch failed: ${resp.status} ${body}`);
}

// ── Router ───────────────────────────────────────────────────────
export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') return corsPreflightResponse();
    if (request.method !== 'POST') return json({ error: 'POST only' }, 405);

    const url = new URL(request.url);
    const path = url.pathname;

    // Parse body for legacy /trigger support
    let body = {};
    try { body = await request.json(); } catch (_) {}

    // Route
    let action;
    if (path === '/boost')       action = 'boost';
    else if (path === '/cancel') action = 'cancel';
    else if (path === '/data')   action = 'data';
    else if (path === '/trigger') {
      // Legacy: dispatch GitHub Actions
      action = body.action || 'log-data';
      const wait = await checkCooldown(action);
      if (wait) return json({ status: 'cooldown', action, retry_in: wait }, 429);
      try {
        const result = await doTrigger(action, env);
        await setCooldown(action);
        return json(result);
      } catch (e) {
        return json({ error: e.message }, 502);
      }
    } else {
      return json({ error: 'Unknown endpoint', endpoints: ['/boost', '/cancel', '/data', '/trigger'] }, 404);
    }

    // Cooldown check
    const wait = await checkCooldown(action);
    if (wait) return json({ status: 'cooldown', action, retry_in: wait }, 429);

    // Vaillant credentials
    const username = env.VAILLANT_USERNAME;
    const password = env.VAILLANT_PASSWORD;
    if (!username || !password) return json({ error: 'VAILLANT credentials not configured' }, 500);

    try {
      // Login
      const tokens = await vaillantLogin(username, password);
      const accessToken = tokens.access_token;

      // Execute action
      let result;
      if (action === 'boost')       result = await doBoost(accessToken);
      else if (action === 'cancel') result = await doCancelBoost(accessToken);
      else if (action === 'data')   result = await doReadData(accessToken, env);

      await setCooldown(action);
      return json(result);
    } catch (e) {
      return json({ error: e.message }, 500);
    }
  },
};
