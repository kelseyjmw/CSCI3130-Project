import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getBids, getListing, submitBid } from '../api/catalog';

export function BidHistory({ bids }) {
    return <section className="catalog-panel">
        <h2>Accepted bids</h2>
        {!bids.length ? <p>No accepted bids yet.</p> : <table>
            <thead><tr><th>Bidder</th><th>Amount</th><th>Time</th><th>Eligibility</th></tr></thead>
            <tbody>{bids.map(bid => <tr key={bid.id}>
                <td>{bid.bidder}</td><td>{bid.currency} {bid.amount}</td>
                <td>{new Date(bid.created_at).toLocaleString(undefined, { timeZoneName: 'short' })}</td>
                <td>{bid.ineligible_reason || 'Eligible'}</td>
            </tr>)}</tbody>
        </table>}
    </section>;
}

export function AuctionOutcome({ listing }) {
    const info = listing.auction_info || {};
    if (!info.completed_at && !['ended', 'removed'].includes(listing.state)) return null;
    return <section className="catalog-panel">
        <h2>Auction outcome</h2>
        <p>{info.outcome}</p>
        {info.winning_amount ? <>
            <p>Winner: {info.winning_bidder}</p>
            <p>Winning price: {listing.currency} {info.winning_amount}</p>
            <p>Payment: {info.payment_status}. The winner is expected to purchase at this amount.</p>
        </> : <p>No winner or order was created.</p>}
    </section>;
}

export default function AuctionPanel({ listing, onChange }) {
    const [bids, setBids] = useState([]);
    const [amount, setAmount] = useState('');
    const [error, setError] = useState('');
    const [message, setMessage] = useState('');
    const [busy, setBusy] = useState(false);
    const info = listing.auction_info;
    useEffect(() => {
        let active = true;
        getBids(listing.id).then(data => { if (active) setBids(data); })
            .catch(failure => { if (active) setError(failure.message); });
        return () => { active = false; };
    }, [listing.id]);

    async function refresh() {
        const [updated, history] = await Promise.all([getListing(listing.id), getBids(listing.id)]);
        onChange(updated);
        setBids(history);
    }

    async function bid(event) {
        event.preventDefault();
        if (!window.confirm(`Confirm your bid of ${listing.currency} ${amount}. If you win, you are expected to purchase at your winning bid amount.`)) return;
        setBusy(true); setError(''); setMessage('');
        try {
            await submitBid(listing.id, amount, listing.currency);
            setAmount('');
            setMessage('Bid accepted.');
            await refresh();
        } catch (failure) {
            setError(failure.fields?.detail || failure.message);
            // Refresh the minimum after another buyer has raised the accepted price.
            try { await refresh(); } catch { /* Keep the original refusal message. */ }
        } finally { setBusy(false); }
    }

    return <>
        <section className="catalog-panel">
            <h2>Bidding</h2>
            {info?.leader && <p>Highest accepted bidder: {info.leader}</p>}
            {!info?.completed_at && <p>Minimum next bid: {listing.currency} {info?.minimum_next_bid ?? 'Not set'}</p>}
            {info?.can_bid ? <form onSubmit={bid}>
                <label className="catalog-field">Your bid ({listing.currency})
                    <input type="number" min={info.minimum_next_bid} step="0.01" required
                        value={amount} disabled={busy} onChange={event => setAmount(event.target.value)} />
                </label>
                <p>The winner is expected to purchase at their winning bid amount.</p>
                <button type="submit" disabled={busy}>Confirm and place bid</button>
            </form> : !info?.completed_at && <p>Bidding requires an active auction and an active, verified buyer account. The seller cannot bid. <Link to="/login">Log in</Link></p>}
            <button type="button" disabled={busy} onClick={() => refresh().catch(failure => setError(failure.message))}>Refresh bids</button>
            {error && <p role="alert" className="catalog-error">{error}</p>}
            {message && <p role="status">{message}</p>}
        </section>
        <AuctionOutcome listing={listing} />
        <BidHistory bids={bids} />
    </>;
}
