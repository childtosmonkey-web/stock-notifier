self.addEventListener('push', function(event) {
    const data = event.data.json();
    const options = {
        body: data.body,
        icon: '/web/icon-192.png',
        image: data.image,
        badge: '/web/icon-72.png',
        data: { ticker: data.ticker },
        requireInteraction: false,
    };
    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    event.waitUntil(clients.openWindow('/'));
});
