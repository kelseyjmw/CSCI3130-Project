import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import ChangePasswordForm from "../components/ChangePasswordForm";
import "./Pages.css";

const API_URL = "http://127.0.0.1:8000/api/accounts";

async function getCsrfToken() {
    const response = await fetch(`${API_URL}/csrf/`, { credentials: "include" });
    const { csrfToken } = await response.json();
    return csrfToken;
}

export default function Account() {
    const { user, refresh } = useAuth();
    const [editing, setEditing] = useState(false);
    const [form, setForm] = useState({email: "", phone_number: "", postal_address: ""});
    const [errors, setErrors] = useState({});
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState("");

    function startEditing() {
        setForm({
            email: user.email,
            phone_number: user.phone_number ?? "",
            postal_address: user.postal_address ?? "",
        });
        setErrors({});
        setMessage("");
        setEditing(true);
    }

    function update(field) {
        return (e) => setForm({ ...form, [field]: e.target.value });
    }

    function fieldError(field) {
        const value = errors[field];
        return Array.isArray(value) ? value.join(" ") : value;
    }

    async function handleSubmit(e) {
        e.preventDefault();
        setSaving(true);
        setErrors({});
        setMessage("");
        try {
            const token = await getCsrfToken();
            const headers = {"Content-Type": "application/json", "X-CSRFToken": token};

            const accountResponse = await fetch(`${API_URL}/me/account/`, {
                method: "PATCH",
                credentials: "include",
                headers,
                body: JSON.stringify({
                    phone_number: form.phone_number,
                    postal_address: form.postal_address,
                }),
            });
            const accountData = await accountResponse.json();
            if (!accountResponse.ok) {
                setErrors(accountData);
                return;
            }

            let note = "Account updated.";
            const newEmail = form.email.trim().toLowerCase();
            if (newEmail !== user.email) {
                const emailResponse = await fetch(`${API_URL}/change-email/`, {
                    method: "POST",
                    credentials: "include",
                    headers,
                    body: JSON.stringify({new_email: newEmail}),
                });
                const emailData = await emailResponse.json();
                if (!emailResponse.ok) {
                    await refresh();
                    setErrors({email: emailData.new_email ?? emailData.detail});
                    return;
                }
                note = `Account updated. A verification link was sent to ${newEmail}. Your email changes once you verify it.`;
            }

            await refresh();
            setMessage(note);
            setEditing(false);
        } catch (err) {
            setErrors({detail: err.message || "Could not save"});
        } finally {
            setSaving(false);
        }
    }

    return (
        <div className="page">
        <h1>Account</h1>

        {message && <p role="status" className="page-banner success">{message}</p>}

        <div className="page-card">
            <div className="page-card-header">
            <h2>Private details</h2>
            {!editing && <button onClick={startEditing}>Edit</button>}
            </div>

            {!editing ? (
            <dl className="page-details">
                <dt>Email</dt>
                <dd>
                {user.email} {user.email_verified ? "(verified)" : "(not verified)"}
                </dd>
                <dt>Phone number</dt>
                <dd>{user.phone_number || "Not set"}</dd>
                <dt>Postal address</dt>
                <dd style={{ whiteSpace: "pre-line" }}>{user.postal_address || "Not set"}</dd>
                <dt>Last login</dt>
                <dd>
                {user.previous_login
                    ? new Date(user.previous_login).toLocaleString()
                    : "First login"}
                </dd>
                    <dt>Account state</dt>
                    <dd>{user.account_state || "Active"}</dd>
                    {user.state_changed_at && (
                        <>
                            <dt>State changed</dt>
                            <dd>{new Date(user.state_changed_at).toLocaleString()}</dd>
                        </>
                    )}
                    {user.suspended_at && (
                        <>
                            <dt>Suspended at</dt>
                            <dd>{new Date(user.suspended_at).toLocaleString()}</dd>
                        </>
                    )}
            </dl>
            ) : (
            <form className="page-form" onSubmit={handleSubmit}>
                <label htmlFor="email">Email</label>
                <input
                id="email"
                type="email"
                value={form.email}
                onChange={update("email")}
                required
                />
                <span className="page-placeholder">
                Changing your email sends a verification link to the new address.
                </span>
                {fieldError("email") && <span role="alert">{fieldError("email")}</span>}

                <label htmlFor="phone_number">Phone number</label>
                <input
                id="phone_number"
                type="tel"
                value={form.phone_number}
                onChange={update("phone_number")}
                maxLength={25}
                />
                {fieldError("phone_number") && <span role="alert">{fieldError("phone_number")}</span>}

                <label htmlFor="postal_address">Postal address</label>
                <textarea
                id="postal_address"
                rows={3}
                value={form.postal_address}
                onChange={update("postal_address")}
                maxLength={300}
                />
                {fieldError("postal_address") && <span role="alert">{fieldError("postal_address")}</span>}

                {fieldError("detail") && <p role="alert">{fieldError("detail")}</p>}
                {fieldError("non_field_errors") && <p role="alert">{fieldError("non_field_errors")}</p>}

                <div className="page-form-actions">
                <button type="submit" disabled={saving}>
                    {saving ? "Saving..." : "Save"}
                </button>
                <button type="button" onClick={() => setEditing(false)} disabled={saving}>
                    Cancel
                </button>
                </div>
            </form>
            )}
            {user.account_state === "Suspended" && (
                <p style={{ color: "red" }}>
                    Your account is suspended. {user.suspension_reason}
                </p>
            )}
        </div>
        <ChangePasswordForm />
        <p className="page-placeholder">
            These details are private and never shown on your public profile.
        </p>
        </div>
    );
}