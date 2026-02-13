/**
 * Cloudflare Worker — proxy for GitHub repository_dispatch.
 * Hides the GitHub token from the public page.
 * Supports multiple event types with separate cooldowns.
 *
 * Environment variables (set in CF dashboard → Worker → Settings → Variables):
 *   GITHUB_TOKEN  — fine-grained PAT with contents:write on the repo
 *
 * Deploy: wrangler deploy
 */

const REPO = 'konradmakosa/vaillant';
const CORS = { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' };

const ACTIONS = {
  'log-data':  { cooldown: 600 },  // 10 min — automatic data logging
  'boost-dhw': { cooldown: 60 },   // 1 min — user-initiated hot water boost
};

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type',
        },
      });
    }

    if (request.method !== 'POST') {
      return new Response(JSON.stringify({ error: 'POST only' }), { status: 405, headers: CORS });
    }

    // Determine action from request body
    let action = 'log-data';
    try {
      const body = await request.json();
      if (body.action && ACTIONS[body.action]) {
        action = body.action;
      }
    } catch (_) {}

    const config = ACTIONS[action];
    const cacheKey = `https://vaillant-trigger.internal/cooldown/${action}`;

    // Persistent cooldown via Cache API (per action)
    const cache = caches.default;
    const cached = await cache.match(cacheKey);
    if (cached) {
      const age = (Date.now() / 1000) - parseFloat(await cached.text());
      if (age < config.cooldown) {
        const wait = Math.ceil(config.cooldown - age);
        return new Response(JSON.stringify({ status: 'cooldown', action, retry_in: wait }), { status: 429, headers: CORS });
      }
    }

    const token = env.GITHUB_TOKEN;
    if (!token) {
      return new Response(JSON.stringify({ error: 'GITHUB_TOKEN not configured' }), { status: 500, headers: CORS });
    }

    const resp = await fetch(`https://api.github.com/repos/${REPO}/dispatches`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'vaillant-cf-worker',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ event_type: action }),
    });

    if (resp.status === 204) {
      const ts = new Response(String(Date.now() / 1000), {
        headers: { 'Cache-Control': `max-age=${config.cooldown}` },
      });
      await cache.put(cacheKey, ts);
      return new Response(JSON.stringify({ status: 'triggered', action }), { headers: CORS });
    }

    const body = await resp.text();
    return new Response(JSON.stringify({ error: 'GitHub API error', status: resp.status, body }), { status: 502, headers: CORS });
  },
};
