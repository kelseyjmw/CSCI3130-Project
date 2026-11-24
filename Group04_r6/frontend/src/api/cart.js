const getCsrfToken = () => {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : '';
};

async function send(url, method, body) {
  const response = await fetch(url, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken(),
    },
    credentials: 'include',
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || 'The cart could not be updated');
    error.response = { status: response.status, data };
    throw error;
  }
  return data;
}

export const getCart = () => send('/api/commerce/cart/', 'GET');

export const addToCart = (listingId, quantity) => send('/api/commerce/cart/items/', 'POST', {
  listing_id: listingId,
  quantity,
});

export const updateQuantity = (listingId, quantity) => send('/api/commerce/cart/items/', 'PATCH', {
  listing_id: listingId,
  quantity,
});

export const removeFromCart = (listingId) => send(`/api/commerce/cart/items/${listingId}/`, 'DELETE');

export const setCartCurrency = (currency) => send('/api/commerce/cart/currency/', 'POST', { currency });

export const returnToCart = () => send('/api/commerce/checkout/return/', 'POST', {});
