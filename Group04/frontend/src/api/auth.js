const API_URL = "http://127.0.0.1:8000/api/accounts";

export async function login(email, password) {
    const response = await fetch(`${API_URL}/login/`, {
        method: "POST",
        credentials: "include",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            email: email,
            password: password,
        }),
    });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error);
    }
    return data;
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