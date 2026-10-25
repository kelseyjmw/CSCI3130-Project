import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import "./Pages.css";

const API_URL = "http://127.0.0.1:8000/api/accounts";

export default function Profile() {
    const { user, refresh } = useAuth();
    const [displayName, setDisplayName] = useState(user.display_name ?? "");
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const [message, setMessage] = useState("");

    async function handleSubmit(e) {
        e.preventDefault();
        setSaving(true);
        setError("");
        setMessage("");
        try {
            const csrfResponse = await fetch(`${API_URL}/csrf/`, {credentials: "include"});
            const { csrfToken } = await csrfResponse.json();

            const response = await fetch(`${API_URL}/me/profile/`, {
                method: "PATCH",
                credentials: "include",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken,
                },
                body: JSON.stringify({display_name: displayName}),
            });
            const data = await response.json();
            if (!response.ok) {
                const fieldError = data.display_name;
                setError(Array.isArray(fieldError) ? fieldError.join(" ") : data.detail || "Could not save.");
                return;
            }
            setDisplayName(data.display_name);
            setMessage("Display name updated.");
            await refresh();
        } catch (err) {
            setError(err.message || "Could not save");
        } finally {
            setSaving(false);
        }
    }

    return(
        <div className="page">
            <h1>{displayName}'s Profile</h1>
            <form className="page-card" onSubmit={handleSubmit}>
                <label htmlFor="display_name">Display Name </label>
                <input
                    id="display_name"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    maxLength={50}
                    required
                />
                <p className="page-placeholder">
                    This is shown on your public profile.
                </p>
                {error && <p role="alert">{error}</p>}
                {message && <p role="status">{message}</p>}
                <button type="submit" disabled={saving}>
                    {saving ? "Saving..." : "Save"}
                </button>
            </form>
            <p>
                <Link to={`/profiles/${user.id}`}>View my public profile</Link>
            </p>
        </div>
    );
}