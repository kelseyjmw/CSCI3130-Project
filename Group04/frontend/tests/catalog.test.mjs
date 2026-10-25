import assert from "node:assert/strict";
import { after, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { createServer } from "vite";

// Use the existing Vite JSX transform and Node's test runner; no extra dependencies.
const server = await createServer({ server: { middlewareMode: true, hmr: false, watch: null } });
after(() => server.close());
const { default: ResultCard } = await server.ssrLoadModule("/src/components/ResultCard.jsx");
const { default: CatalogResults } = await server.ssrLoadModule("/src/components/CatalogResults.jsx");
const { default: Catalog } = await server.ssrLoadModule("/src/pages/Catalog.jsx");
const listing = { id: 42, title: "Working laptop", primary_image: "/primary.png", price: "200.00", currency: "CAD" };
function render(component, props) {
    return renderToStaticMarkup(createElement(MemoryRouter, null, createElement(component, props)));
}

test("catalog page renders its filters and loading state", () => {
    const html = render(Catalog);
    assert.match(html, /Apply filters/);
    assert.match(html, /Clear filters/);
    assert.match(html, /Currency code/);
    assert.match(html, /Search titles and descriptions/);
    assert.match(html, /Loading listings/);
});

test("result card shows essentials and links to the correct listing", () => {
    const html = render(ResultCard, listing);
    assert.match(html, /href="\/listings\/42"/);
    assert.match(html, /<h2>Working laptop<\/h2>/);
    assert.match(html, /<img[^>]+src="\/primary.png"/);
    assert.match(html, /CAD 200\.00/);
});

test("catalog restores filters and sorting from its URL", () => {
    const html = renderToStaticMarkup(createElement(MemoryRouter, {
        initialEntries: ["/catalog?q=laptop&currency=USD&max_price=500&ordering=price&page=2"],
    }, createElement(Catalog)));
    assert.match(html, /id="catalog-q"[^>]*value="laptop"/);
    assert.match(html, /Min price \(USD\)/);
    assert.match(html, /id="catalog-max-price"[^>]*value="500"/);
    assert.match(html, /value="price" selected=""/);
});

test("result link carries the search context for the listing back link", () => {
    const from = "?q=laptop&currency=CAD&page=2";
    const card = ResultCard({ ...listing, from });
    assert.equal(card.props.to, "/listings/42");
    assert.deepEqual(card.props.state, { from });
});

test("missing image has a placeholder and titles are escaped", () => {
    const html = render(ResultCard, { ...listing, primary_image: null, title: "<script>alert(1)</script>" });
    assert.match(html, /No image available/);
    assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
    assert.doesNotMatch(html, /<script/);
});

test("count displays all matches rather than just the current page", () => {
    const html = render(CatalogResults, {
        data: { count: 13, results: [listing], next: "/?page=2", previous: null }, page: 1,
    });
    assert.match(html, /13 listings found/);
    assert.match(html, /Results pages/);
    assert.match(html, /Page 1/);
});

test("zero matches show the count and a useful message without cards", () => {
    const html = render(CatalogResults, { data: { count: 0, results: [] } });
    assert.match(html, /0 listings found/);
    assert.match(html, /No listings match/);
    assert.match(html, /clearing filters/);
    assert.doesNotMatch(html, /class="catalog-card"/);
});

test("results display the current page and total number of pages", () => {
    const html = render(CatalogResults, {
        data: { count: 30, total_pages: 3, results: [listing], previous: "/?page=1", next: "/?page=3" }, page: 2,
    });
    assert.match(html, /30 listings found/);
    assert.match(html, /Page 2 of 3/);
});
