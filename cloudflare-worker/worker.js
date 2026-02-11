/**
 * Cloudflare Worker — proxy for GitHub repository_dispatch.
 * Hides the GitHub token from the public page.
 *
 * Environment variables (set in CF dashboard → Worker → Settings → Variables):
 *   GITHUB_TOKEN  — fine-grained PAT with contents:write on the repo
 *
 * Deploy: wrangler deploy
 */

const REPO = 'konradmakosa/vaillant';
const EVENT_TYPE = 'log-data';
const COOLDOWN_SECONDS = 600; // 10 min cooldown (Vaillant API quota)
const CACHE_KEY = 'https://vaillant-trigger.internal/last-trigger';

const CORS = { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' };

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

    // Persistent cooldown via Cache API
    const cache = caches.default;
    const cached = await cache.match(CACHE_KEY);
    if (cached) {
      const age = (Date.now() / 1000) - parseFloat(await cached.text());
      if (age < COOLDOWN_SECONDS) {
        const wait = Math.ceil(COOLDOWN_SECONDS - age);
        return new Response(JSON.stringify({ status: 'cooldown', retry_in: wait }), { status: 429, headers: CORS });
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
      body: JSON.stringify({ event_type: EVENT_TYPE }),
    });

    if (resp.status === 204) {
      // Store timestamp in cache for COOLDOWN_SECONDS
      const ts = new Response(String(Date.now() / 1000), {
        headers: { 'Cache-Control': `max-age=${COOLDOWN_SECONDS}` },
      });
      await cache.put(CACHE_KEY, ts);
      return new Response(JSON.stringify({ status: 'triggered' }), { headers: CORS });
    }

    const body = await resp.text();
    return new Response(JSON.stringify({ error: 'GitHub API error', status: resp.status, body }), { status: 502, headers: CORS });
  },
};
