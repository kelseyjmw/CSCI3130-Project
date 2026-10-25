import { useState } from "react";
import "../pages/Pages.css"

const API_URL = "http://127.0.0.1:8000/api/accounts";

async function getCsrfToken() {
  const response = await fetch(`${API_URL}/csrf/`, { credentials: "include" });
  const { csrfToken } = await response.json();
  return csrfToken;
}

const EMPTY = {current_password: "", new_password: "", confirm_password: ""};

export default function ChangePasswordForm() {
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState(EMPTY);
    const [errors, setErrors] = useState({});
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState("");

    function update(field) {
        return (e) => setForm({...form, [field]: e.target.value});
    }

    function fieldError(field) {
        const value = errors[field];
        return Array.isArray(value) ? value.join(" ") : value;
    }

    function close() {
        setOpen(false);
        setForm(EMPTY);
        setErrors({});
    }

    async function handleSubmit(event) {
        event.preventDefault();
        setErrors({});
        setMessage("");

        if (form.new_password !== form.confirm_password) {
            setErrors({confirm_password: "The new passwords do not match"});
            return;
        }

        setSaving(true);
        try {
            const token = await getCsrfToken();
            const response = await fetch(`${API_URL}/password/change/`, {
                method: "POST",
                credentials: "include",
                headers: {"Content-Type": "application/json", "X-CSRFToken": token},
                body: JSON.stringify({
                    current_password: form.current_password,
                    new_password: form.new_password,
                }),
            });
            const data = await response.json();
            if (!response.ok) {
                setErrors(data);
                return;
            }
            setMessage(data.detail || "Your password has been changed.");
            close();
        } catch (err) {
            setErrors({detail: err.message || "Could not change password."});
        } finally {
            setSaving(false);
        }
    }

    return(
        <div className="page-card" style={{marginTop: 16}}>
            <div className="page-card-header">
                <h2>Password</h2>
                {!open && (
                    <button onClick={() => {setMessage(""); setOpen(true)}}>
                        Change Password
                    </button>
                )}
            </div>

            {message && <p role="status" className="page-banner success">{message}</p>}

            {open && (
                <form className="page-form" onSubmit={handleSubmit}>
                    <label htmlFor="current_password">Current Password</label>
                    <input
                        id="current_password"
                        type="password"
                        autoComplete="current-password"
                        value={form.current_password}
                        onChange={update("current_password")}
                        required
                    />
                    {fieldError("current_password") && (
                        <span role="alert">{fieldError("current_password")}</span>
                    )}

                    <label htmlFor="new_password">New Password</label>
                    <input
                        id="new_password"
                        type="password"
                        autoComplete="new-password"
                        value={form.new_password}
                        onChange={update("new_password")}
                        required
                    />
                    {fieldError("new_password") && (
                        <span role="alert">{fieldError("new_password")}</span>
                    )}

                    <label htmlFor="confirm_password">Confirm New Password</label>
                    <input
                        id="confirm_password"
                        type="password"
                        autoComplete="new-password"
                        value={form.confirm_password}
                        onChange={update("confirm_password")}
                        required
                    />
                    {fieldError("confirm_password") && (
                        <span role="alert">{fieldError("confirm_password")}</span>
                    )}

                    {fieldError("detail") && <p role="alert">{fieldError("detail")}</p>}
                    {fieldError("non_field_errors") && (
                        <p role="alert">{fieldError("non_field_errors")}</p>
                    )}

                    <p className="page-placeholder">
                        Changing your password signs you out of your other devices.
                    </p>

                    <div className="page-form-actions">
                        <button type="submit" disabled={saving}>
                        {saving ? "Saving..." : "Update password"}
                        </button>
                        <button type="button" onClick={close} disabled={saving}>
                        Cancel
                        </button>
                    </div>
                </form>
            )}
        </div>
    );
}