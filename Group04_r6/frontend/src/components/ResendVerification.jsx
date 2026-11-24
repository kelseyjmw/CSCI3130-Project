import { useState } from 'react';
import { Link } from 'react-router-dom';

export default function ResendVerification() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState('idle'); // idle | loading | success | error
  const [message, setMessage] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus('loading');
    setMessage('');

    // Rule: normalize email by trimming whitespace and lowercasing
    const normalizedEmail = email.trim().toLowerCase();

    try {
      const response = await fetch('http://127.0.0.1:8000/api/accounts/resend-verification/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email: normalizedEmail }),
      });

      const data = await response.json();

      if (response.ok) {
        setStatus('success');
        setMessage(
          data.detail ||
            'If that account exists and is unverified, a new link has been sent to your email.'
        );
      } else {
        setStatus('error');
        setMessage(
          data.detail ||
            data.email?.[0] ||
            'Failed to send verification link. Please check the email address and try again.'
        );
      }
    } catch (err) {
      setStatus('error');
      setMessage('Unable to connect to the server. Please check your network and try again.');
    }
  };

  return (
    <div
      style={{
        maxWidth: '440px',
        margin: '60px auto',
        padding: '32px 24px',
        backgroundColor: '#161b22',
        border: '1px solid #30363d',
        borderRadius: '10px',
        color: '#f0f6fc',
        boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
      }}
    >
      <h2 style={{ textAlign: 'center', marginBottom: '16px', fontSize: '22px' }}>
        Resend Verification Link
      </h2>
      <p style={{ fontSize: '14px', color: '#8b949e', textAlign: 'center', marginBottom: '24px' }}>
        Enter your registered email address to receive a fresh verification link.
      </p>

      {message && (
        <div
          style={{
            marginBottom: '20px',
            padding: '12px 14px',
            borderRadius: '6px',
            backgroundColor: status === 'success' ? '#064e3b' : '#7f1d1d',
            color: status === 'success' ? '#6ee7b7' : '#fca5a5',
            border: `1px solid ${status === 'success' ? '#047857' : '#b91c1c'}`,
            fontSize: '14px',
            lineHeight: '1.4',
            textAlign: 'center',
          }}
        >
          {message}
        </div>
      )}

      {status === 'success' ? (
        <div style={{ textAlign: 'center', marginTop: '16px' }}>
          <p style={{ fontSize: '13px', color: '#8b949e', marginBottom: '20px' }}>
            Check your inbox (or terminal in testing mode) for the verification message.
          </p>
          <Link
            to="/login"
            style={{
              display: 'inline-block',
              padding: '10px 24px',
              backgroundColor: '#2563eb',
              color: '#fff',
              borderRadius: '6px',
              textDecoration: 'none',
              fontWeight: 600,
              fontSize: '14px',
            }}
          >
            Go to Log In
          </Link>
        </div>
      ) : (
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '20px' }}>
            <label
              htmlFor="resend-email"
              style={{ display: 'block', marginBottom: '6px', fontSize: '14px', fontWeight: 500 }}
            >
              Email Address
            </label>
            <input
              id="resend-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="netid@dal.ca"
              style={{
                width: '100%',
                padding: '10px 12px',
                borderRadius: '6px',
                border: '1px solid #30363d',
                backgroundColor: '#0d1117',
                color: '#f0f6fc',
                fontSize: '14px',
                boxSizing: 'border-box',
              }}
            />
          </div>

          <button
            type="submit"
            disabled={status === 'loading'}
            style={{
              width: '100%',
              padding: '12px',
              backgroundColor: '#2563eb',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              fontSize: '15px',
              fontWeight: 600,
              cursor: status === 'loading' ? 'not-allowed' : 'pointer',
              opacity: status === 'loading' ? 0.7 : 1,
            }}
          >
            {status === 'loading' ? 'Sending...' : 'Send Verification Link'}
          </button>

          <div
            style={{
              marginTop: '20px',
              display: 'flex',
              justifyContent: 'space-between',
              fontSize: '13px',
            }}
          >
            <Link to="/login" style={{ color: '#58a6ff', textDecoration: 'none' }}>
              Back to Log In
            </Link>
            <Link to="/register" style={{ color: '#58a6ff', textDecoration: 'none' }}>
              Create an account
            </Link>
          </div>
        </form>
      )}
    </div>
  );
}