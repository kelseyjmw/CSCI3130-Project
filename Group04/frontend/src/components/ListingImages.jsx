import { useState } from "react";
import { removeImage, reorderImages, saveImageDescription, uploadImage } from "../api/catalog";

export default function ListingImages({ listing, onChange }) {
    const [descriptions, setDescriptions] = useState({});
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const images = listing.images;
    async function run(operation) {
        setBusy(true);
        setError("");
        try { await operation(); }
        catch (failure) { setError(failure.message); }
        finally { setBusy(false); }
    }
    function upload(event) {
        const file = event.target.files[0];
        event.target.value = "";
        if (!file) return;
        if (file.size > 10 * 1024 * 1024) {
            setError("Choose an image of 10 MB or smaller.");
            return;
        }
        run(async () => onChange([...images, await uploadImage(listing.id, file)]));
    }
    function move(index, direction) {
        const ordered = [...images];
        [ordered[index], ordered[index + direction]] = [ordered[index + direction], ordered[index]];
        run(async () => onChange(await reorderImages(listing.id, ordered.map((image) => image.id))));
    }
    return <section className="catalog-panel">
        <h2>Images ({images.length}/5)</h2>
        <p>JPEG, PNG or WebP, up to 10 MB each. The first image is the primary image.</p>
        {error && <p className="catalog-error" role="alert">{error}</p>}
        <div className="catalog-image-grid">
            {images.map((image, index) => <div className="catalog-image-editor" key={image.id}>
                <img src={image.file} alt={image.description || `Listing image ${index + 1}`} />
                <strong>{index === 0 ? "Primary image" : `Image ${index + 1}`}</strong>
                <label>Image description
                    <input value={descriptions[image.id] ?? image.description} onChange={(event) => setDescriptions({ ...descriptions, [image.id]: event.target.value })} />
                </label>
                <div className="catalog-actions">
                    <button type="button" disabled={busy} onClick={() => run(async () => {
                        const saved = await saveImageDescription(listing.id, image.id, descriptions[image.id] ?? image.description);
                        onChange(images.map((entry) => entry.id === saved.id ? saved : entry));
                    })}>Save description</button>
                    <button type="button" aria-label={`Move image ${index + 1} earlier`} disabled={busy || index === 0} onClick={() => move(index, -1)}>Earlier</button>
                    <button type="button" aria-label={`Move image ${index + 1} later`} disabled={busy || index === images.length - 1} onClick={() => move(index, 1)}>Later</button>
                    <button type="button" disabled={busy || (listing.state !== "draft" && images.length === 1)} onClick={() => run(async () => {
                        await removeImage(listing.id, image.id);
                        onChange(images.filter((entry) => entry.id !== image.id));
                    })}>Remove</button>
                </div>
            </div>)}
        </div>
        <label className="catalog-upload">Add an image
            <input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy || images.length >= 5} onChange={upload} />
        </label>
        {busy && <p role="status">Updating images…</p>}
    </section>;
}
