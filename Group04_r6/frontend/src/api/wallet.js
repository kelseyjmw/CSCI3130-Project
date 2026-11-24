const WALLET_BASE_URL = '/api/accounts/wallet';

const getCsrfToken = () => {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : '';
};

const defaultHeaders = () => ({
  'Content-Type': 'application/json',

  'X-CSRFToken': getCsrfToken(),
});

export const getWallet = async () => {
  const response = await fetch(`${WALLET_BASE_URL}/`, {
    method: 'GET',
    headers: defaultHeaders(),
    credentials: 'include',
  });
  if (response.status === 404) {
    return null; // No wallet initialized yet
  }
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.detail || 'Failed to fetch wallet');
    error.response = { status: response.status, data };
    throw error;
  }
  return data;
};

export const createWallet = async (currency) => {
  const response = await fetch(`${WALLET_BASE_URL}/create/`, {
    method: 'POST',
    headers: defaultHeaders(),
    credentials: 'include',
    body: JSON.stringify({ currency }),
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || 'Failed to create wallet');
    error.response = { status: response.status, data };
    throw error;
  }
  return data;
};

export const topUpWallet = async ({ amount, cardNumber, cvv, expiry }) => {
  const response = await fetch(`${WALLET_BASE_URL}/topup/`, {
    method: 'POST',
    headers: defaultHeaders(),
    credentials: 'include',
    body: JSON.stringify({
      amount,
      card_number: cardNumber,
      cvv,
      expiry,
    }),
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error('Top-up failed');
    error.response = { status: response.status, data };
    throw error;
  }
  return data;
};