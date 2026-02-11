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
const COOLDOWN_SECONDS = 600; // ignore repeated calls within 10 min (Vaillant API quota)

let lastTrigger = 0;

export default {
  async fetch(request, env) {
    // CORS preflight
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
      return new Response(JSON.stringify({ error: 'POST only' }), {
        status: 405,
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' },
      });
    }

    // Cooldown — don't spam GitHub API
    const now = Date.now() / 1000;
    if (now - lastTrigger < COOLDOWN_SECONDS) {
      const wait = Math.ceil(COOLDOWN_SECONDS - (now - lastTrigger));
      return new Response(JSON.stringify({ status: 'cooldown', retry_in: wait }), {
        status: 429,
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' },
      });
    }

    const token = env.GITHUB_TOKEN;
    if (!token) {
      return new Response(JSON.stringify({ error: 'GITHUB_TOKEN not configured' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' },
      });
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
      lastTrigger = now;
      return new Response(JSON.stringify({ status: 'triggered' }), {
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' },
      });
    }

    const body = await resp.text();
    return new Response(JSON.stringify({ error: 'GitHub API error', status: resp.status, body }), {
      status: 502,
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' },
    });
  },
};
