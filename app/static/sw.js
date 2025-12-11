const CACHE_NAME = 'gabutpay-cache-v1';
const OFFLINE_URL = '/offline';

// List of files to cache on install
const urlsToCache = [
  OFFLINE_URL,
  '/static/css/bootstrap.min.css',
  '/static/css/modern.css',
  '/static/js/bootstrap.bundle.min.js',
  '/static/js/main.js',
  '/static/images/logo.png'
];

// Install event: cache the app shell
self.addEventListener('install', event => {
  console.log('[Service Worker] Install');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('[Service Worker] Caching app shell');
        return cache.addAll(urlsToCache);
      })
  );
});

// Activate event: clean up old caches
self.addEventListener('activate', event => {
  console.log('[Service Worker] Activate');
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            console.log('[Service Worker] Removing old cache', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  return self.clients.claim();
});

// Fetch event: Hybrid strategy
self.addEventListener('fetch', event => {
  // Only handle GET requests
  if (event.request.method !== 'GET' || !event.request.url.startsWith('http')) {
    return;
  }

  // Strategy 1: Network-First for HTML navigation requests.
  if (event.request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        // Try the network first
        const networkResponse = await fetch(event.request);
        // If successful, cache it and return it
        const cache = await caches.open(CACHE_NAME);
        cache.put(event.request, networkResponse.clone());
        return networkResponse;
      } catch (error) {
        // If the network fails, try the cache
        console.log('[Service Worker] Fetch failed; trying cache.', error);
        const cachedResponse = await caches.match(event.request);
        if (cachedResponse) {
          return cachedResponse;
        }
        // If the cache also fails, show the offline page
        const offlinePage = await caches.match(OFFLINE_URL);
        return offlinePage;
      }
    })());
    return;
  }

  // Strategy 2: Stale-While-Revalidate for all other assets (CSS, JS, images).
  event.respondWith(
    caches.match(event.request).then(cachedResponse => {
      const fetchPromise = fetch(event.request).then(networkResponse => {
        if (networkResponse.ok) {
          caches.open(CACHE_NAME).then(cache => {
            cache.put(event.request, networkResponse.clone());
          });
        }
        return networkResponse;
      });
      // Return cached response immediately if available, otherwise wait for network
      return cachedResponse || fetchPromise;
    })
  );
});

// Push event: display the notification
self.addEventListener('push', event => {
  console.log('[Service Worker] Push Received.');
  const data = event.data.json();
  console.log('[Service Worker] Push data:', data);

  const title = data.title || 'GabutPay';
  const options = {
    body: data.body || 'Anda memiliki notifikasi baru.',
    icon: '/static/images/logo.png',
    badge: '/static/images/logo.png'
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

// Notification click event: focus or open the app
self.addEventListener('notificationclick', event => {
  console.log('[Service Worker] Notification click Received.');

  event.notification.close();

  event.waitUntil(
    clients.matchAll({
      type: "window",
      includeUncontrolled: true
    }).then(clientList => {
      // If a window for the app is already open, focus it.
      for (const client of clientList) {
        // The URL check can be refined depending on your app's structure
        if (new URL(client.url).pathname === '/' && 'focus' in client) {
          return client.focus();
        }
      }
      // Otherwise, open a new window.
      if (clients.openWindow) {
        return clients.openWindow('/');
      }
    })
  );
});
