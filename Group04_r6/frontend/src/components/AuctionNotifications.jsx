import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getAuctionNotifications } from '../api/catalog';

export default function AuctionNotifications() {
    const [notifications, setNotifications] = useState([]);
    const [error, setError] = useState('');
    useEffect(() => {
        let active = true;
        let loading = false;
        async function refresh() {
            if (loading) return;
            loading = true;
            try {
                const data = await getAuctionNotifications();
                if (active) { setNotifications(data); setError(''); }
            } catch (failure) {
                if (active) setError(failure.message);
            } finally { loading = false; }
        }
        refresh();
        const interval = window.setInterval(refresh, 15000);
        window.addEventListener('focus', refresh);
        return () => {
            active = false;
            window.clearInterval(interval);
            window.removeEventListener('focus', refresh);
        };
    }, []);
    return <section className="page-card" aria-live="polite">
        <h2>Auction notifications and orders</h2>
        {error && <p role="alert">{error}</p>}
        {!error && !notifications.length && <p>No auction notifications yet.</p>}
        {notifications.map(notification => <article key={notification.id}>
            <p>{notification.message}</p>
            <p>{new Date(notification.created_at).toLocaleString(undefined, { timeZoneName: 'short' })}</p>
            <p className="cart-actions">
                <Link to={`/listings/${notification.listing_id}`}>View auction</Link>
                {notification.order_id && (
                    <Link to={`/auction-orders/${notification.order_id}`}>
                        {notification.payment_status === 'Pending' && notification.message?.startsWith('You won')
                            ? 'Pay auction order'
                            : 'View auction order'}
                    </Link>
                )}
            </p>
        </article>)}
    </section>;
}
