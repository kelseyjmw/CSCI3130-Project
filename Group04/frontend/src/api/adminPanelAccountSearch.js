const API_URL = "http://127.0.0.1:8000";

// Account search for admin panel 'Accounts' page
export async function searchAccounts({search="", page=1}){
    const params = new URLSearchParams({page: String(page)});
    if (search.trim()) {
        params.set("search", search.trim());
    }

    const response = await fetch(`${API_URL}/api/accounts/admin/accounts/?${params}`, {
        method: "GET",
        credentials: "include",
    });

    if (!response.ok) {
        const error = newError(
            response.status === 403
            ? "You do not have permission to view accounts."
            : "Could not load accounts."
        );
        error.status = response.status;
        throw error;
    }

    return response.json();
}