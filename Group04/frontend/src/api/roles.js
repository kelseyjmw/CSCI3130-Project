const API_URL = "http://127.0.0.1:8000";

export async function setUserRoles(userId, roles) {
    const response = await fetch(`${API_URL}/api/security/users/${userId}/`, {
        method: "PUT",
        credentials: "include",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({ roles }),
    });

    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.error || data.detail || "Could not save roles");
    }

    return data;
}
