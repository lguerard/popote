// Service worker minimal : il rend Popote installable (écran d'accueil,
// cible du menu « Partager » d'Android). Aucune mise en cache : les
// recettes viennent toujours du serveur, jamais d'une copie périmée.
self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()))
self.addEventListener('fetch', () => {})
