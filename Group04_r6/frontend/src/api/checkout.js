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
    const error = new Error(data.detail || 'Checkout could not be updated');
    error.response = { status: response.status, data };
    throw error;
  }
  return data;
}

export const startCheckout = (guestEmail) => send('/api/commerce/checkout/', 'POST', {
  guest_email: guestEmail || '',
});

export const getCheckoutReview = () => send('/api/commerce/checkout/review/', 'GET');

export const confirmCheckout = () => send('/api/commerce/checkout/confirm/', 'POST', {});

export const returnToCart = () => send('/api/commerce/checkout/return/', 'POST', {});

export const saveDeliveryAddress = (address) => send('/api/commerce/checkout/address/', 'POST', address);

export const payOrder = (orderId) => send(`/api/commerce/orders/${orderId}/pay/`, 'POST', {});

export const getOrder = (orderId) => send(`/api/commerce/orders/${orderId}/`, 'GET');

export const getGuestOrder = (token) => send(`/api/commerce/orders/guest/${encodeURIComponent(token)}/`, 'GET');

export const getAuctionOrder = (auctionOrderId) => send(`/api/commerce/auction-orders/${auctionOrderId}/`, 'GET');

export const getAuctionOrderQuote = (auctionOrderId) => send(`/api/commerce/auction-orders/${auctionOrderId}/quote/`, 'GET');

export const payAuctionOrder = (auctionOrderId, address) => send(`/api/commerce/auction-orders/${auctionOrderId}/pay/`, 'POST', { address });
