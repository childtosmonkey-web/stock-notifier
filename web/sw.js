self.addEventListener('push', function(event) {
    let data;
    try {
        data = event.data.json();
    } catch(e) {
        data = { title: event.data ? event.data.text() : 'Stock Notifier', body: '' };
    }
    const options = {
        body: data.body,
        icon: '/web/icon-192.png',
        image: data.image,
        badge: '/web/icon-72.png',
        data: {
            ticker: data.ticker,
            price: data.price,
            change_pct: data.change_pct,
            change: data.change,
            chart_url: data.chart_url,
        },
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
