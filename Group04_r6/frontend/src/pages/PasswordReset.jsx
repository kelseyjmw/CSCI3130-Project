import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import PasswordStrength from '../components/PasswordStrength';
import { passwordError } from '../utils/passwordStrength';

export default function PasswordReset() {
    const { token } = useParams();
    const { refresh } = useAuth();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmation, setConfirmation] = useState('');
    const [error, setError] = useState('');
    const [message, setMessage] = useState('');
    const [saving, setSaving] = useState(false);

    async function submit(event) {
        event.preventDefault();
        setError('');
        if (token) {
            const invalid = passwordError(password);
            if (invalid || password !== confirmation) {
                setError(invalid || 'Passwords do not match.');
                return;
            }
        }
        setSaving(true);
        try {
            const endpoint = token ? `${encodeURIComponent(token)}/` : 'request/';
            const response = await fetch(`http://127.0.0.1:8000/api/accounts/password-reset/${endpoint}`, {
                method: 'POST',
                credentials: 'omit',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(token ? { password } : { email: email.trim().toLowerCase() }),
            });
            const data = await response.json();
            if (!response.ok) {
                setError(Object.values(data).flat().join(' '));
                return;
            }
            setPassword('');
            setConfirmation('');
            setMessage(data.detail);
            if (token) await refresh();
        } catch {
            setError('Unable to connect to the server. Please try again.');
        } finally {
            setSaving(false);
        }
    }

    return (
        <div id="app-form">
            <h1>{token ? 'Reset password' : 'Forgot password'}</h1>
            {error && <p role="alert">{error}</p>}
            {message ? <p role="status">{message}</p> : (
                <form onSubmit={submit}>
                    {token ? <>
                        <label htmlFor="reset-password">New password</label>
                        <input id="reset-password" type="password" autoComplete="new-password"
                            value={password} onChange={event => setPassword(event.target.value)} required />
                        <PasswordStrength password={password} />
                        <label htmlFor="reset-confirmation">Confirm password</label>
                        <input id="reset-confirmation" type="password" autoComplete="new-password"
                            value={confirmation} onChange={event => setConfirmation(event.target.value)} required />
                    </> : <>
                        <label htmlFor="reset-email">Email address</label>
                        <input id="reset-email" type="email" autoComplete="email"
                            value={email} onChange={event => setEmail(event.target.value)} required />
                    </>}
                    <button disabled={saving} type="submit">
                        {saving ? 'Please wait...' : token ? 'Reset password' : 'Send reset link'}
                    </button>
                </form>
            )}
            {token && <p><Link to="/forgot-password">Request a new reset link</Link></p>}
            <p><Link to="/login">Back to log in</Link></p>
        </div>
    );
}
