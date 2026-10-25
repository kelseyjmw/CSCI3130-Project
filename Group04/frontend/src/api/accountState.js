const API_URL = "http://127.0.0.1:8000";

export async function setAccountState(userId, accountState, reason) {
    const response = await fetch(`${API_URL}/api/security/account-state/${userId}/`, {
        method: "PUT",
        credentials: "include",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({ account_state: accountState, reason }),
    });

    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.error || data.detail || "Could not update account state");
    }

    return data;
}
