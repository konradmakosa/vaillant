const CACHE_NAME = 'wanna-v1';
const ASSETS = [
    '/',
    '/index.html',
    '/manifest.json',
    '/icon-192.png',
    '/icon-512.png',
];

self.addEventListener('install', (e) => {
    e.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS))
    );
    self.skipWaiting();
});

self.addEventListener('activate', (e) => {
    e.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', (e) => {
    const url = new URL(e.request.url);

    // Always fetch CSV data from network (fresh data)
    if (url.hostname === 'raw.githubusercontent.com') {
        e.respondWith(fetch(e.request));
        return;
    }

    // Always fetch worker API from network
    if (url.hostname.includes('workers.dev')) {
        e.respondWith(fetch(e.request));
        return;
    }

    // Cache-first for app shell
    e.respondWith(
        caches.match(e.request).then(cached => cached || fetch(e.request))
    );
});
