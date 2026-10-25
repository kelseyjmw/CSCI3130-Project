import { useState } from "react";
import { Link } from "react-router-dom";
import { listingAction } from "../api/catalog";

const labels = { publish: "Publish", pause: "Pause", resume: "Resume", end: "End listing", remove: "Remove listing" };

export default function ListingActions({ listing, onChange }) {
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    async function run(action) {
        if (action === "remove" && !window.confirm("Remove this listing? It will no longer be publicly visible.")) return;
        setBusy(true);
        setError("");
        try {
            onChange(await listingAction(listing.id, action));
        } catch (failure) {
            setError(failure.message);
        } finally {
            setBusy(false);
        }
    }
    return <div>
        <div className="catalog-actions">
            {listing.available_actions.includes("edit") && <Link className="catalog-button" to={`/listings/${listing.id}/edit`}>{listing.details_locked ? "Increase stock" : "Edit listing"}</Link>}
            {listing.available_actions.filter((action) => action !== "edit").map((action) =>
                <button key={action} type="button" disabled={busy} onClick={() => run(action)}>{labels[action]}</button>)}
        </div>
        {error && <p className="catalog-error" role="alert">{error}</p>}
    </div>;
}
