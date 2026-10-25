import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { categoryPath, createListing, getAttributes, getCategories, getListing, listingAction, saveListing } from "../api/catalog";
import { useAuth } from "../context/AuthContext";
import ListingImages from "../components/ListingImages";
import "./Catalog.css";

const emptyForm = { title: "", description: "", category: "", condition: "", price: "", currency: "CAD", quantity: "", country: "CA", postal_code: "", ends_at: "", attribute_values: {} };
const conditions = [["new", "New"], ["new_no_package", "New, no package"], ["refurbished", "Refurbished"], ["used_very_good", "Used, very good"], ["used_good", "Used, good"], ["for_parts", "For parts"]];

function toForm(listing) {
    let endsAt = "";
    if (listing.ends_at) {
        const date = new Date(listing.ends_at);
        endsAt = new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    }
    return { ...listing, category: listing.category ?? "", price: listing.price ?? "", quantity: listing.quantity ?? "", ends_at: endsAt };
}

function Editor({ id }) {
    const { user } = useAuth();
    const navigate = useNavigate();
    const [listing, setListing] = useState(null);
    const [form, setForm] = useState(emptyForm);
    const [categories, setCategories] = useState([]);
    const [attributes, setAttributes] = useState([]);
    const [errors, setErrors] = useState({});
    const [message, setMessage] = useState("");
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    useEffect(() => {
        let active = true;
        Promise.all([getCategories(), id ? getListing(id) : Promise.resolve(null)]).then(([tree, item]) => {
            if (active) { setCategories(tree); setListing(item); if (item) setForm(toForm(item)); }
        }).catch((failure) => { if (active) setErrors({ detail: failure.message }); })
            .finally(() => { if (active) setLoading(false); });
        return () => { active = false; };
    }, [id]);
    useEffect(() => {
        let active = true;
        (form.category ? getAttributes(form.category) : Promise.resolve([])).then((data) => { if (active) setAttributes(data); })
            .catch((failure) => { if (active) setErrors({ detail: failure.message }); });
        return () => { active = false; };
    }, [form.category]);
    function change(name, value) { setForm((current) => ({ ...current, [name]: value })); }
    function payload() {
        if (listing?.details_locked) return { quantity: form.quantity === "" ? null : Number(form.quantity) };
        const values = { ...form.attribute_values };
        for (const attribute of attributes) {
            if (attribute.type === "number" && values[attribute.code] !== "" && values[attribute.code] != null) values[attribute.code] = Number(values[attribute.code]);
        }
        return {
            title: form.title, description: form.description, category: form.category ? Number(form.category) : null,
            condition: form.condition, price: form.price === "" ? null : form.price, currency: form.currency,
            quantity: form.quantity === "" ? null : Number(form.quantity), country: form.country,
            postal_code: form.postal_code, attribute_values: values,
            ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : null,
        };
    }
    async function save(publish = false) {
        setBusy(true); setErrors({}); setMessage("");
        try {
            const saved = id ? await saveListing(id, payload()) : await createListing(payload());
            if (publish) {
                await listingAction(saved.id, "publish");
                navigate(`/listings/${saved.id}`);
            } else if (!id) {
                navigate(`/listings/${saved.id}/edit`, { replace: true });
            } else {
                setListing(saved); setForm(toForm(saved)); setMessage(saved.state === "draft" ? "Draft saved." : "Changes saved.");
            }
        } catch (failure) {
            setErrors(failure.fields || { detail: failure.message });
        } finally { setBusy(false); }
    }
    function field(name, label, type = "text", props = {}) {
        return <label className="catalog-field">{label}<input type={type} value={form[name]} onChange={(event) => change(name, event.target.value)} {...props} />
            {errors[name] && <span className="catalog-error">{errors[name]}</span>}
        </label>;
    }
    if (loading) return <main className="catalog-page" role="status">Loading listing form…</main>;
    if ((id && !listing?.available_actions.includes("edit")) || (!id && !user.roles?.includes("Seller"))) {
        return <main className="catalog-page"><p role="alert">You do not have permission to edit this listing.</p><Link to="/my-listings">My listings</Link></main>;
    }
    return <main className="catalog-page">
        <Link to="/my-listings">Back to my listings</Link><h1>{id ? "Edit listing" : "Create listing"}</h1>
        {user.account_state === "Suspended" && <p className="catalog-notice">Your account is suspended. You can save changes, but cannot publish or resume sales.</p>}
        {Object.keys(errors).length > 0 && <div role="alert" className="catalog-notice catalog-error">{errors.detail || errors.non_field_errors || errors.state || errors.images || "Please check the highlighted fields."}</div>}
        {message && <p role="status" className="catalog-notice">{message}</p>}
        {listing?.details_locked && <p className="catalog-notice">This listing has a purchase. Its details and images are locked. You can only increase the stock quantity.</p>}
        <form className="catalog-panel catalog-form" noValidate onSubmit={(event) => { event.preventDefault(); save(); }}>
            <fieldset className="catalog-details-fields" disabled={listing?.details_locked}>
            {field("title", "Title", "text", { maxLength: 80 })}
            <label className="catalog-field">Description<textarea rows="6" maxLength={5000} value={form.description} onChange={(event) => change("description", event.target.value)} />{errors.description && <span className="catalog-error">{errors.description}</span>}</label>
            <label className="catalog-field">Category<select value={form.category} onChange={(event) => {
                setAttributes([]);
                setForm((current) => ({ ...current, category: event.target.value, attribute_values: {} }));
            }}><option value="">Select a category</option>{categories.filter((entry) => entry.is_leaf).map((entry) => <option key={entry.id} value={entry.id}>{categoryPath(entry, categories)}</option>)}</select>{errors.category && <span className="catalog-error">{errors.category}</span>}</label>
            <label className="catalog-field">Condition<select value={form.condition} onChange={(event) => change("condition", event.target.value)}><option value="">Select a condition</option>{conditions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>{errors.condition && <span className="catalog-error">{errors.condition}</span>}</label>
            <div className="catalog-form-grid">{field("price", "Price", "number", { min: "0.01", step: "0.01" })}{field("currency", "Currency code", "text", { maxLength: 3, placeholder: "CAD" })}</div>
            <div className="catalog-form-grid">{field("country", "Country code", "text", { maxLength: 2, placeholder: "CA" })}{field("postal_code", "Postal code", "text", { maxLength: 20 })}{field("ends_at", "End time (optional, local time)", "datetime-local")}</div>
            {attributes.length > 0 && <fieldset><legend>Category details</legend>{attributes.map((attribute) => <label className="catalog-field" key={attribute.code}>
                {attribute.name}{attribute.required ? " (required to publish)" : " (optional)"}
                {attribute.type === "choice" ? <select value={form.attribute_values[attribute.code] ?? ""} onChange={(event) => change("attribute_values", { ...form.attribute_values, [attribute.code]: event.target.value })}>
                    <option value="">Select an option</option>{attribute.options.map((option) => <option value={option} key={option}>{option}</option>)}
                </select> : <input type={attribute.type === "number" ? "number" : "text"} step={attribute.type === "number" ? "any" : undefined} min={attribute.min_value ?? undefined} max={attribute.max_value ?? undefined} value={form.attribute_values[attribute.code] ?? ""} onChange={(event) => change("attribute_values", { ...form.attribute_values, [attribute.code]: event.target.value })} />}
                {errors[`attribute_values.${attribute.code}`] && <span className="catalog-error">{errors[`attribute_values.${attribute.code}`]}</span>}
            </label>)}</fieldset>}
            </fieldset>
            {field("quantity", "Stock quantity", "number", { min: listing?.details_locked ? (listing.quantity || 0) + 1 : 0, step: 1 })}
            <div className="catalog-actions"><button disabled={busy} type="submit">{busy ? "Saving…" : !listing || listing.state === "draft" ? "Save draft" : "Save changes"}</button>
                {listing?.available_actions.includes("publish") && <button disabled={busy} type="button" onClick={() => save(true)}>Save and publish</button>}
                {id && <Link to={`/listings/${id}`}>View listing</Link>}
            </div>
        </form>
        {listing?.details_locked ? <section className="catalog-panel"><h2>Images</h2><div className="catalog-image-grid">{listing.images.map((image) => <img key={image.id} src={image.file} alt={image.description || listing.title} style={{ width: "100%" }} />)}</div></section> : listing ? <ListingImages listing={listing} onChange={(images) => setListing((current) => ({ ...current, images }))} /> : <p className="catalog-notice">Save a draft to add images. Publishing requires one to five images.</p>}
    </main>;
}

export default function ListingForm() {
    const { id } = useParams();
    return <Editor key={id || "new"} id={id} />;
}
