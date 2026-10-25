import { useEffect, useState } from "react";
import { Link, useParams, useLocation } from "react-router-dom";
import { categoryPath, getAttributes, getCategories, getListing } from "../api/catalog";
import ListingActions from "../components/ListingActions";
import "./Catalog.css";

export default function ListingDetail() {
    const { id } = useParams();
    const location = useLocation();
    const backTo = `/catalog${location.state?.from ?? ""}`;
    const [listing, setListing] = useState(null);
    const [categories, setCategories] = useState([]);
    const [attributes, setAttributes] = useState([]);
    const [error, setError] = useState("");
    useEffect(() => {
        let active = true;
        Promise.all([getListing(id), getCategories()]).then(async ([item, tree]) => {
            const definitions = item.category ? await getAttributes(item.category) : [];
            if (active) { setListing(item); setCategories(tree); setAttributes(definitions); }
        }).catch((failure) => { if (active) setError(failure.message); });
        return () => { active = false; };
    }, [id]);
    if (error) return <main className="catalog-page"><p role="alert" className="catalog-error">{error}</p><Link to={backTo}>Back to catalog</Link></main>;
    if (!listing) return <main className="catalog-page" role="status">Loading listing…</main>;
    const category = categories.find((entry) => entry.id === listing.category);
    return <main className="catalog-page">
        <Link to={backTo}>Back to catalog</Link>
        <div className="catalog-heading"><h1>{listing.title || "Untitled draft"}</h1><span className="catalog-status">{listing.state.replaceAll("_", " ")}</span></div>
        {!listing.is_available && <p className="catalog-notice">This listing is not available for purchase.</p>}
        <div className="catalog-detail-grid">
            <div className="catalog-gallery">{listing.images.map((image, index) => <figure key={image.id}><img src={image.file} alt={image.description || `${listing.title}, image ${index + 1}`} />{image.description && <figcaption>{image.description}</figcaption>}</figure>)}</div>
            <section className="catalog-panel">
                <p className="catalog-price">{listing.currency} {listing.price ?? "Price not set"}</p>
                <p>{listing.is_available ? `Available · ${listing.quantity} in stock` : `Stock: ${listing.quantity ?? "Not set"}`}</p>
                <p>{listing.condition_display}</p><p>{category && categoryPath(category, categories)}</p>
                <p>{listing.country} · {listing.postal_code}</p>
                <p>Seller: <Link to={`/profiles/${listing.seller}`}>{listing.seller_name}</Link></p>
                {listing.ends_at && <p>End time: {new Date(listing.ends_at).toLocaleString()}</p>}
                <p>Last updated: {new Date(listing.updated_at).toLocaleString()}</p>
                <ListingActions listing={listing} onChange={setListing} />
            </section>
        </div>
        <section className="catalog-panel"><h2>Description</h2><p className="catalog-description">{listing.description || "No description yet."}</p></section>
        {attributes.length > 0 && <section className="catalog-panel"><h2>Item details</h2><dl className="catalog-attributes">{attributes.map((attribute) => <div key={attribute.code}><dt>{attribute.name}</dt><dd>{String(listing.attribute_values[attribute.code] ?? "Not set")}</dd></div>)}</dl></section>}
    </main>;
}
