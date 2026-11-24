const API_URL = "http://127.0.0.1:8000/api/accounts";

async function csrfHeaders() {
    const response = await fetch(`${API_URL}/csrf/`, { credentials: "include" });
    const data = await response.json();
    if (!response.ok || !data.csrfToken) {
        throw new Error(data.error || "Could not prepare the request. Please try again.");
    }
    return { "Content-Type": "application/json", "X-CSRFToken": data.csrfToken };
}

async function postJson(path, body) {
    const response = await fetch(`${API_URL}/${path}/`, {
        method: "POST",
        credentials: "include",
        headers: await csrfHeaders(),
        body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || data.detail || "Request failed.");
    }
    return data;
}

export function login(email, password) {
    return postJson("login", { email, password });
}

export function verifyLoginMfa(code, recoveryCode = false) {
    return postJson(
        "login/verify-mfa",
        recoveryCode ? { recovery_code: code } : { code },
    );
}

export function startTwoFactorSetup(password) {
    return postJson("two-factor/setup", password ? { password } : {});
}

export function confirmTwoFactorSetup(code) {
    return postJson("two-factor/confirm", { code });
}

export async function getMe() {
    const response = await fetch(`${API_URL}/me/`, {
        method: "GET",
        credentials: "include",
    });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || "Not authenticated");
    }
    return data;
}

export async function logout() {
    const response = await fetch(`${API_URL}/logout/`, {
        method: "POST",
        credentials: "include",
    });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || "Logout failed");
    }
    return data;
}
