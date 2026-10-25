import { useState } from 'react';
import { Link } from "react-router-dom";

export default function Register() {
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    passwordConfirm: '',
  });

  const [errors, setErrors] = useState({});
  const [serverMessage, setServerMessage] = useState('');
  const [loading, setLoading] = useState(false);

  // Score password strength (0 to 4)
  const calculateStrength = (pass) => {
    if (!pass) return { score: 0, label: '', color: '#e5e7eb' };
    let score = 0;
    if (pass.length >= 6) score += 1;
    if (pass.length >= 10) score += 1;
    if (/\d/.test(pass)) score += 1;
    if (/[!@#$%^&*(),.?":{}|<>]/.test(pass)) score += 1;

    switch (score) {
      case 1:
        return { score: 1, label: 'Weak', color: '#ef4444' };
      case 2:
        return { score: 2, label: 'Fair', color: '#f59e0b' };
      case 3:
        return { score: 3, label: 'Good', color: '#3b82f6' };
      case 4:
        return { score: 4, label: 'Strong', color: '#10b981' };
      default:
        return { score: 0, label: 'Too Weak', color: '#ef4444' };
    }
  };

  const strength = calculateStrength(formData.password);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    if (errors[name]) {
      setErrors((prev) => ({ ...prev, [name]: '' }));
    }
  };

  const validate = () => {
    const newErrors = {};

    // Email check
    const cleanedEmail = formData.email.trim();
    if (!cleanedEmail) {
      newErrors.email = 'Email is required.';
    } else if (!/\S+@\S+\.\S+/.test(cleanedEmail)) {
      newErrors.email = 'Please enter a valid email address.';
    }

    // Specification rules: >= 6 chars, 1 digit, 1 special char
    if (!formData.password) {
      newErrors.password = 'Password is required.';
    } else if (formData.password.length < 6) {
      newErrors.password = 'Password must be at least 6 characters long.';
    } else if (!/\d/.test(formData.password)) {
      newErrors.password = 'Password must contain at least one digit (0-9).';
    } else if (!/[!@#$%^&*(),.?":{}|<>]/.test(formData.password)) {
      newErrors.password = 'Password must contain at least one special character (e.g., @, #, !).';
    }

    // Match check
    if (formData.password !== formData.passwordConfirm) {
      newErrors.passwordConfirm = 'Passwords do not match.';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setServerMessage('');

    if (!validate()) return;

    setLoading(true);

    try {
      const response = await fetch('http://127.0.0.1:8000/api/accounts/register/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: formData.email.trim().toLowerCase(),
          password: formData.password,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        setServerMessage(
          'Account created successfully! Check your email (or terminal console) for your verification link.'
        );
        setFormData({ email: '', password: '', passwordConfirm: '' });
      } else {
        if (typeof data === 'object') {
          const apiErrors = {};
          for (const key in data) {
            apiErrors[key] = Array.isArray(data[key]) ? data[key].join(' ') : data[key];
          }
          setErrors(apiErrors);
        } else {
          setServerMessage('Registration failed. Please check your details.');
        }
      }
    } catch (err) {
      setServerMessage('Unable to reach the server. Make sure the backend is running.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div id="app-form">
      <h1>Create Buyer Account</h1>
      {serverMessage && (
        <div style={{ padding: '10px', marginBottom: '16px', background: '#eef2ff', borderRadius: '4px', color: '#1e3a8a' }}>
          {serverMessage}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div>
          <label>Email Address</label>
          <input
            type="email"
            name="email"
            value={formData.email}
            onChange={handleChange}
            placeholder="example@email.com"
          />
          {errors.email && <span style={{ color: 'red', fontSize: '13px' }}>{errors.email}</span>}
        </div>

        <div>
          <label>Password</label>
          <input
            type="password"
            name="password"
            value={formData.password}
            onChange={handleChange}
            placeholder="At least 6 chars, 1 digit, 1 special symbol"
          />
          {errors.password && <span style={{ color: 'red', fontSize: '13px' }}>{errors.password}</span>}

          {formData.password && (
            <div style={{ marginTop: '8px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                <span>Strength:</span>
                <span style={{ fontWeight: 'bold', color: strength.color }}>{strength.label}</span>
              </div>
              <div style={{ height: '6px', width: '100%', backgroundColor: '#e5e7eb', borderRadius: '3px', overflow: 'hidden' }}>
                <div
                  style={{
                    height: '100%',
                    width: `${(strength.score / 4) * 100}%`,
                    backgroundColor: strength.color,
                    transition: 'width 0.3s ease',
                  }}
                />
              </div>
            </div>
          )}
        </div>

        <div>
          <label>Confirm Password</label>
          <input
            type="password"
            name="passwordConfirm"
            value={formData.passwordConfirm}
            onChange={handleChange}
            placeholder="Re-enter password"
          />
          {errors.passwordConfirm && <span style={{ color: 'red', fontSize: '13px' }}>{errors.passwordConfirm}</span>}
        </div>

        <button
          type="submit"
          disabled={loading}
          style={{
            cursor: loading ? 'not-allowed' : 'pointer',
          }}
        >
          {loading ? 'Creating Account...' : 'Register'}
        </button>
        <p style={{ marginTop: '6px' }}>
          Already have an account?
          <Link to="/login">Log In</Link>
        </p>
      </form>
    </div>
  );
}