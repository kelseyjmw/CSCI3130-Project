import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { calculateStrength, passwordError } from "../src/utils/passwordStrength.js";

test("password strength scores length, digits and special characters", () => {
    for (const [password, score, label] of [
        ["", 0, ""], ["abcdef", 1, "Weak"], ["abcdef12", 2, "Fair"],
        ["Foo12@", 3, "Good"], ["LongPass12!", 4, "Strong"],
    ]) {
        const strength = calculateStrength(password);
        assert.equal(strength.score, score);
        assert.equal(strength.label, label);
    }
});

test("the score updates when a digit or special character is added", () => {
    assert.equal(calculateStrength("abcdef").score, 1);
    assert.equal(calculateStrength("abcdef1").score, 2);
    assert.equal(calculateStrength("abcdef1!").score, 3);
    assert.equal(calculateStrength("abcdefgh1!").score, 4);
});

test("validation accepts six characters and punctuation, but rejects missing requirements", () => {
    for (const password of ['Foo12@', 'Foo12_', 'Foo12-', ' Foo1@ ']) {
        assert.equal(passwordError(password), '', password);
    }
    for (const password of ['', 'Ab1!', 'LettersOnly', 'Letters123', 'SpecialOnly!', 'Foo12 ', 'Foo١٢@', 'Aa1!😀']) {
        assert.notEqual(passwordError(password), '', password);
    }
});

test("invalid passwords cannot receive a Good or Strong rating", () => {
    for (const password of ['VeryLongPassword1', 'VeryLongPassword!', '1!a']) {
        assert.ok(calculateStrength(password).score <= 2, password);
    }
});

test("strength indicator shows the requirements and updates its accessible score", async () => {
    const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false, watch: null } });
    try {
        const { default: PasswordStrength } = await server.ssrLoadModule('/src/components/PasswordStrength.jsx');
        const render = password => renderToStaticMarkup(createElement(PasswordStrength, { password }));
        assert.match(render(''), /at least 6 characters/);
        assert.doesNotMatch(render(''), /role="meter"/);
        assert.match(render('Foo12@'), /aria-valuenow="3" aria-valuetext="Good"/);
        assert.match(render('LongPass12!'), /aria-valuenow="4" aria-valuetext="Strong"/);
        assert.match(render('LongPassword1'), /aria-valuenow="2" aria-valuetext="Fair"/);
    } finally {
        await server.close();
    }
});
