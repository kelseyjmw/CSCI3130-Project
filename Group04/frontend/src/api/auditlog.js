const API_URL = "http://127.0.0.1:8000";

export async function getAuditLog(page = 1) {
    const response = await fetch(`${API_URL}/api/accounts/admin/audit-log/?page=${page}`, {
        method: "GET",
        credentials: "include",
    });

    if (!response.ok) {
        const error = new Error(
            response.status === 403
                ? "Only administrators can view the audit log."
                : "Could not load the audit log."
        );
        error.status = response.status;
        throw error;
    }

    // { count, next, previous, results }
    return response.json();
}