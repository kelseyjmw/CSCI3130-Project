import assert from "node:assert/strict";
import { after, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { createServer } from "vite";

const server = await createServer({ server: { middlewareMode: true, hmr: false, watch: null } });
after(() => server.close());
const { default: Cart } = await server.ssrLoadModule("/src/pages/Cart.jsx");
const { default: Checkout } = await server.ssrLoadModule("/src/pages/Checkout.jsx");
const { default: Order } = await server.ssrLoadModule("/src/pages/Order.jsx");
const { default: GuestOrder } = await server.ssrLoadModule("/src/pages/GuestOrder.jsx");
const { AuthProvider } = await server.ssrLoadModule("/src/context/AuthContext.jsx");

test("cart page shows its heading and loading state", () => {
    const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(Cart)));
    assert.match(html, /<h1>Cart<\/h1>/);
    assert.match(html, /Loading cart/);
});

test("checkout and order pages show their loading states", () => {
    const checkout = renderToStaticMarkup(createElement(MemoryRouter, null,
        createElement(AuthProvider, null, createElement(Checkout))));
    assert.match(checkout, /<h1>Checkout<\/h1>/);
    assert.match(checkout, /Loading checkout/);
    const order = renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: ["/orders/4"] },
        createElement(Routes, null, createElement(Route, { path: "/orders/:orderId", element: createElement(Order) }))));
    assert.match(order, /Loading order/);
    const guest = renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: ["/orders/guest/link"] },
        createElement(Routes, null, createElement(Route, { path: "/orders/guest/:token", element: createElement(GuestOrder) }))));
    assert.match(guest, /<h1>Guest order<\/h1>/);
});
