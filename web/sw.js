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
        data: { ticker: data.ticker },
        requireInteraction: false,
    };
    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    const d = event.notification.data || {};
    const params = new URLSearchParams({
        ticker: d.ticker || '',
        price: d.price || '',
        change_pct: d.change_pct || '',
        change: d.change || '',
        chart_url: d.chart_url || '',
    });
    event.waitUntil(clients.openWindow('/?' + params.toString()));
});
