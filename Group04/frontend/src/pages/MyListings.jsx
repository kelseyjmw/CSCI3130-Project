import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getMyListings } from "../api/catalog";
import { useAuth } from "../context/AuthContext";
import ListingActions from "../components/ListingActions";
import "./Catalog.css";

export default function MyListings() {
    const { user } = useAuth();
    const [listings, setListings] = useState([]);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(true);
    const seller = user.roles?.includes("Seller");
    useEffect(() => {
        let active = true;
        getMyListings().then((data) => { if (active) setListings(data); })
            .catch((failure) => { if (active) setError(failure.message); })
            .finally(() => { if (active) setLoading(false); });
        return () => { active = false; };
    }, []);
    return <main className="catalog-page">
        <div className="catalog-heading"><h1>My listings</h1>{seller && user.email_verified && <Link className="catalog-button" to="/listings/new">Create listing</Link>}</div>
        {user.account_state === "Suspended" && <p className="catalog-notice">Your listings are hidden while your account is suspended. You can prepare drafts, but cannot publish or resume sales.</p>}
        {!seller && <p>Become an approved seller to create listings. <Link to="/applications">Seller applications</Link></p>}
        {!user.email_verified && <p className="catalog-notice">Verify your email before creating or editing listings.</p>}
        {error && <p role="alert" className="catalog-error">{error}</p>}
        {loading ? <p role="status">Loading your listings…</p> : !error && !listings.length ? <p className="catalog-empty">You have no listings yet.</p> : listings.map((listing) => <article className="catalog-panel" key={listing.id}>
            <div className="catalog-heading"><h2><Link to={`/listings/${listing.id}`}>{listing.title || "Untitled draft"}</Link></h2><span className="catalog-status">{listing.state.replaceAll("_", " ")}</span></div>
            <p>{listing.currency} {listing.price ?? "Price not set"} · Stock: {listing.quantity ?? "Not set"}</p>
            <p>Last updated: {new Date(listing.updated_at).toLocaleString()}</p>
            <ListingActions listing={listing} onChange={(updated) => setListings((items) => items.map((item) => item.id === updated.id ? updated : item))} />
        </article>)}
    </main>;
}
