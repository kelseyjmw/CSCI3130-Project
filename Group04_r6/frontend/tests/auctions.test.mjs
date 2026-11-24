import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { createServer } from 'vite';
import { submitBid } from '../src/api/catalog.js';

const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false, watch: null } });
after(() => server.close());
const { default: AuctionPanel, BidHistory, AuctionOutcome } = await server.ssrLoadModule('/src/components/AuctionPanel.jsx');
const render = (component, props) => renderToStaticMarkup(createElement(MemoryRouter, null, createElement(component, props)));
const listing = {
    id: 42, currency: 'CAD', auction_info: {
        can_bid: true, minimum_next_bid: '27.00', leader: 'Bidder anonymous',
    },
};

test('bidding shows currency, the current minimum and the purchase obligation', () => {
    const html = render(AuctionPanel, { listing, onChange() {} });
    assert.match(html, /Minimum next bid: CAD 27\.00/);
    assert.match(html, /min="27\.00"/);
    assert.match(html, /Confirm and place bid/);
    assert.match(html, /expected to purchase at their winning bid amount/);
    assert.match(html, /Highest accepted bidder: Bidder anonymous/);
});

test('history presents accepted amounts, timestamps and separate ineligibility decisions', () => {
    const html = render(BidHistory, { bids: [
        { id: 1, bidder: 'Bidder anonymous', amount: '25.00', currency: 'CAD', created_at: '2026-11-02T12:00:00Z', ineligible_reason: 'Buyer suspended before completion.' },
    ] });
    assert.match(html, /CAD 25\.00/);
    assert.match(html, /Bidder anonymous/);
    assert.match(html, /Buyer suspended before completion/);
    assert.match(html, /2026/);
});

test('auction outcome distinguishes a pending winning order from no sale', () => {
    const completed = { ...listing, auction_info: { completed_at: '2026-11-02T13:00:00Z', outcome: 'Highest eligible bid wins.', winning_amount: '30.00', winning_bidder: 'Bidder anonymous', payment_status: 'Pending' } };
    assert.match(render(AuctionOutcome, { listing: completed }), /Winning price: CAD 30\.00/);
    assert.match(render(AuctionOutcome, { listing: completed }), /Payment: Pending/);
    completed.auction_info.winning_amount = null;
    assert.match(render(AuctionOutcome, { listing: completed }), /No winner or order was created/);
    assert.match(render(AuctionOutcome, { listing: { ...listing, state: 'ended' } }), /No winner or order was created/);
});

test('bid submission preserves decimal text and sends the session CSRF token', async t => {
    const calls = [];
    t.mock.method(globalThis, 'fetch', async (url, options) => {
        calls.push([url, options]);
        return { ok: true, status: 200, json: async () => url.endsWith('/csrf/') ? { csrfToken: 'test-csrf' } : { amount: '25.01' } };
    });
    await submitBid(42, '25.01', 'CAD');
    assert.match(calls[1][0], /\/listings\/42\/bids\/$/);
    assert.equal(calls[1][1].credentials, 'include');
    assert.equal(calls[1][1].headers['X-CSRFToken'], 'test-csrf');
    assert.deepEqual(JSON.parse(calls[1][1].body), { amount: '25.01', currency: 'CAD' });
});
