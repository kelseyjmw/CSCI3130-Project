import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { createServer } from 'vite';

const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false, watch: null } });
after(() => server.close());
const { default: PasswordReset } = await server.ssrLoadModule('/src/pages/PasswordReset.jsx');
const { default: Login } = await server.ssrLoadModule('/src/pages/Login.jsx');
const { AuthProvider } = await server.ssrLoadModule('/src/context/AuthContext.jsx');
function render(path, route, component = PasswordReset) {
    return renderToStaticMarkup(createElement(AuthProvider, null,
        createElement(MemoryRouter, { initialEntries: [path] },
            createElement(Routes, null, createElement(Route, {
                path: route, element: createElement(component),
            })))));
}

test('login offers password reset before any two-factor challenge', () => {
    const html = render('/login', '/login', Login);
    assert.match(html, /id="login-password"/);
    assert.match(html, /href="\/forgot-password"/);
    assert.doesNotMatch(html, /id="enrollment-code"/);
});

test('reset request page asks for email and links back to login', () => {
    const html = render('/forgot-password', '/forgot-password');
    assert.match(html, /type="email"/);
    assert.match(html, /Send reset link/);
    assert.match(html, /href="\/login"/);
    assert.doesNotMatch(html, /type="password"/);
});

test('email reset link opens password and confirmation fields with the shared requirements', () => {
    const html = render('/reset-password/test-token', '/reset-password/:token');
    assert.equal((html.match(/type="password"/g) || []).length, 2);
    assert.match(html, /at least 6 characters/);
    assert.match(html, /href="\/forgot-password"/);
    assert.doesNotMatch(html, /type="email"/);
});
