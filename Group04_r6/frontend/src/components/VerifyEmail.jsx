import { useEffect, useState, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';

export default function VerifyEmail() {
  const { token } = useParams();
  const [status, setStatus] = useState('verifying');
  const [message, setMessage] = useState('Verifying your email address, please wait...');
  const hasRequested = useRef(false);

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setMessage('Invalid verification link: missing token.');
      return;
    }

    // Prevent duplicate request in React StrictMode
    if (hasRequested.current) return;
    hasRequested.current = true;

    const verifyToken = async () => {
      try {
        const response = await fetch(`http://127.0.0.1:8000/api/accounts/verify-email/${token}/`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
        });

        const data = await response.json();

        if (response.ok) {
          setStatus('success');
          setMessage(data.detail || 'Your email has been successfully verified! You can now log in.');
        } else {
          setStatus('error');
          setMessage(data.detail || 'This verification link is invalid or has expired.');
        }
      } catch (err) {
        setStatus('error');
        setMessage('Unable to connect to the verification server. Please try again later.');
      }
    };

    verifyToken();
  }, [token]);

  return (
    <div
      style={{
        maxWidth: '440px',
        margin: '60px auto',
        padding: '32px 24px',
        backgroundColor: '#161b22',
        border: '1px solid #30363d',
        borderRadius: '10px',
        textAlign: 'center',
        color: '#f0f6fc',
        boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
      }}
    >
      <h2 style={{ marginBottom: '16px', fontSize: '22px' }}>Email Verification</h2>

      <div
        style={{
          margin: '20px 0',
          padding: '14px',
          borderRadius: '6px',
          backgroundColor:
            status === 'success' ? '#064e3b' : status === 'error' ? '#7f1d1d' : '#1e293b',
          color:
            status === 'success' ? '#6ee7b7' : status === 'error' ? '#fca5a5' : '#93c5fd',
          border: `1px solid ${
            status === 'success' ? '#047857' : status === 'error' ? '#b91c1c' : '#3b82f6'
          }`,
          fontSize: '14px',
          lineHeight: '1.5',
        }}
      >
        {message}
      </div>

      {status === 'success' && (
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
          }}
        >
          Go to Log In
        </Link>
      )}

      {status === 'error' && (
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
          <Link
            to="/register"
            style={{
              display: 'inline-block',
              padding: '10px 18px',
              backgroundColor: '#374151',
              color: '#f3f4f6',
              borderRadius: '6px',
              textDecoration: 'none',
              fontSize: '14px',
            }}
          >
            Register Again
          </Link>
          <Link
            to="/resend-verification"
            style={{
              display: 'inline-block',
              padding: '10px 18px',
              backgroundColor: '#2563eb',
              color: '#fff',
              borderRadius: '6px',
              textDecoration: 'none',
              fontSize: '14px',
            }}
          >
            Resend Link
          </Link>
        </div>
      )}
    </div>
  );
}