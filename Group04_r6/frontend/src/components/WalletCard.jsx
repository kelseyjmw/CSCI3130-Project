import React, { useState, useEffect } from 'react';
import { getWallet, createWallet, topUpWallet } from '../api/wallet';

export default function WalletCard() {
  const [wallet, setWallet] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Currency initialization state
  const [selectedCurrency, setSelectedCurrency] = useState('CAD');

  // Top-up modal states
  const [showTopUp, setShowTopUp] = useState(false);
  const [amount, setAmount] = useState('');
  const [cardNumber, setCardNumber] = useState('');
  const [cvv, setCvv] = useState('');
  const [expiry, setExpiry] = useState('');
  const [formErrors, setFormErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);

  const fetchWallet = async () => {
    try {
      setLoading(true);
      setError('');
      const data = await getWallet();
      setWallet(data);
    } catch (err) {
      if (err.response && err.response.status === 404) {
        setWallet(null); // Not initialized yet
      } else {
        setError(err.response?.data?.detail || 'Failed to fetch wallet information.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWallet();
  }, []);

  const handleCreateWallet = async (e) => {
    e.preventDefault();
    try {
      setSubmitting(true);
      setError('');
      const data = await createWallet(selectedCurrency);
      setWallet(data);
      setSuccess(`Wallet initialized with currency: ${selectedCurrency}`);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to create wallet.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleTopUpSubmit = async (e) => {
    e.preventDefault();
    setFormErrors({});
    setError('');
    setSuccess('');
    setSubmitting(true);

    try {
      const updated = await topUpWallet({
        amount,
        cardNumber,
        cvv,
        expiry,
      });
      setWallet(updated);
      setSuccess(`Successfully added ${amount} ${updated.currency} to your wallet!`);
      setShowTopUp(false);
      setAmount('');
      setCardNumber('');
      setCvv('');
      setExpiry('');
    } catch (err) {
      const errData = err.response?.data;
      if (typeof errData === 'object' && errData !== null) {
        setFormErrors(errData);
      } else {
        setError('Top-up failed. Please check your card information.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <div className="wallet-card"><p>Loading wallet...</p></div>;
  }

  // If wallet has not been initialized yet
  if (!wallet) {
    return (
      <div className="card shadow-sm mb-4">
        <div className="card-body">
          <h4 className="card-title">Setup Your Marketplace Wallet</h4>
          <p className="card-text text-muted">
            Choose your permanent wallet currency. Once selected, your wallet currency cannot be changed.
          </p>
          {error && <div className="alert alert-danger">{error}</div>}
          <form onSubmit={handleCreateWallet} className="d-flex align-items-center gap-2">
            <select
              className="form-select w-auto"
              value={selectedCurrency}
              onChange={(e) => setSelectedCurrency(e.target.value)}
            >
              <option value="CAD">CAD - Canadian Dollar</option>
              <option value="USD">USD - US Dollar</option>
            </select>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Creating...' : 'Initialize Wallet'}
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="card shadow-sm mb-4">
      <div className="card-body">
        <div className="d-flex justify-content-between align-items-center mb-3">
          <div>
            <h5 className="mb-0 text-muted">Balance & Controls</h5>
            <span className="badge bg-secondary me-2">{wallet.currency}</span>
            {wallet.is_guest && <span className="badge bg-warning text-dark">Guest Wallet</span>}
          </div>
          <button className="btn btn-success" onClick={() => setShowTopUp(true)}>
            + Top Up Funds
          </button>
        </div>

        {wallet.warning && (
          <div className="alert alert-warning py-2 mb-3">
            <small>⚠️ {wallet.warning}</small>
          </div>
        )}

        {success && <div className="alert alert-success">{success}</div>}
        {error && <div className="alert alert-danger">{error}</div>}

        <div className="p-3 bg-light rounded mb-4">
          <div className="text-muted small">Current Balance</div>
          <div className="display-6 fw-bold text-success">
            ${parseFloat(wallet.balance).toFixed(2)} {wallet.currency}
          </div>
        </div>

        {/* Top-Up Modal / Dropdown */}
        {showTopUp && (
          <div className="border border-success rounded p-3 mb-4 bg-white">
            <div className="d-flex justify-content-between align-items-center mb-2">
              <h5 className="mb-0">Top-Up Wallet ({wallet.currency})</h5>
              <button
                type="button"
                className="btn-close"
                onClick={() => setShowTopUp(false)}
              ></button>
            </div>
            <form onSubmit={handleTopUpSubmit}>
              <div className="mb-2">
                <label className="form-label small fw-bold">Amount ({wallet.currency})</label>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  className={`form-control ${formErrors.amount ? 'is-invalid' : ''}`}
                  placeholder="e.g. 50.00"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  required
                />
                {formErrors.amount && <div className="invalid-feedback">{formErrors.amount}</div>}
              </div>

              <div className="mb-2">
                <label className="form-label small fw-bold">Card Number (16 digits)</label>
                <input
                  type="text"
                  maxLength="16"
                  className={`form-control ${formErrors.card_number ? 'is-invalid' : ''}`}
                  placeholder="1234567812345678"
                  value={cardNumber}
                  onChange={(e) => setCardNumber(e.target.value)}
                  required
                />
                {formErrors.card_number && (
                  <div className="invalid-feedback">{formErrors.card_number}</div>
                )}
              </div>

              <div className="row g-2 mb-3">
                <div className="col-6">
                  <label className="form-label small fw-bold">CVV (3 digits)</label>
                  <input
                    type="password"
                    maxLength="3"
                    className={`form-control ${formErrors.cvv ? 'is-invalid' : ''}`}
                    placeholder="007"
                    value={cvv}
                    onChange={(e) => setCvv(e.target.value)}
                    required
                  />
                  {formErrors.cvv && <div className="invalid-feedback">{formErrors.cvv}</div>}
                </div>
                <div className="col-6">
                  <label className="form-label small fw-bold">Expiry (MM/YYYY)</label>
                  <input
                    type="text"
                    placeholder="12/2026"
                    className={`form-control ${formErrors.expiry ? 'is-invalid' : ''}`}
                    value={expiry}
                    onChange={(e) => setExpiry(e.target.value)}
                    required
                  />
                  {formErrors.expiry && (
                    <div className="invalid-feedback">{formErrors.expiry}</div>
                  )}
                </div>
              </div>

              <div className="d-flex gap-2">
                <button type="submit" className="btn btn-primary btn-sm" disabled={submitting}>
                  {submitting ? 'Processing...' : 'Confirm Top-Up'}
                </button>
                <button
                  type="button"
                  className="btn btn-outline-secondary btn-sm"
                  onClick={() => setShowTopUp(false)}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Transaction History */}
        <h5 className="mt-4 mb-2">Transaction History</h5>
        {!wallet.transactions || wallet.transactions.length === 0 ? (
          <p className="text-muted small">No transactions yet.</p>
        ) : (
          <div className="table-responsive">
            <table className="table table-sm table-striped">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Amount</th>
                  <th>Resulting Balance</th>
                  <th>Reference</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {wallet.transactions.map((tx) => (
                  <tr key={tx.id}>
                    <td>
                      <span
                        className={`badge ${
                          tx.transaction_type === 'TOP_UP'
                            ? 'bg-primary'
                            : tx.transaction_type === 'RECEIPT'
                            ? 'bg-success'
                            : 'bg-danger'
                        }`}
                      >
                        {tx.transaction_type}
                      </span>
                    </td>
                    <td>
                      {tx.transaction_type === 'PAYMENT' ? '-' : '+'}
                      {parseFloat(tx.amount).toFixed(2)} {tx.currency}
                    </td>
                    <td>
                      ${parseFloat(tx.resulting_balance).toFixed(2)} {tx.currency}
                    </td>
                    <td>
                      <code>{tx.reference || '—'}</code>
                    </td>
                    <td className="small text-muted">
                      {new Date(tx.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}