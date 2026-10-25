const API = "http://127.0.0.1:8000/api";

function flattenErrors(value, prefix = "") {
    if (Array.isArray(value)) return { [prefix || "detail"]: value.join(" ") };
    if (value && typeof value === "object") {
        return Object.assign({}, ...Object.entries(value).map(([key, entry]) =>
            flattenErrors(entry, prefix ? `${prefix}.${key}` : key)));
    }
    return { [prefix || "detail"]: String(value) };
}

async function request(path, method = "GET", body) {
    const headers = {};
    if (method !== "GET") {
        const csrfResponse = await fetch(`${API}/accounts/csrf/`, { credentials: "include" });
        if (!csrfResponse.ok) throw new Error("Could not prepare the request. Please sign in again.");
        headers["X-CSRFToken"] = (await csrfResponse.json()).csrfToken;
    }
    if (body !== undefined && !(body instanceof FormData)) headers["Content-Type"] = "application/json";
    const response = await fetch(`${API}/catalog/${path}`, {
        method, credentials: "include", headers,
        body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
    });
    const data = response.status === 204 ? null : await response.json().catch(() => ({ detail: "Request failed. Please try again." }));
    if (!response.ok) {
        const fields = flattenErrors(data);
        const error = new Error(Object.values(fields).join(" "));
        error.fields = fields;
        error.status = response.status;
        throw error;
    }
    return data;
}

export const getListings = (filters = {}) => {
    const params = new URLSearchParams();
    for (const [name, value] of Object.entries(filters)) {
        if (value != null && (value !== "" || name === "currency")) params.set(name, value);
    }
    return request(`listings/?${params}`);
};
export const getMyListings = () => request("listings/mine/");
export const getListing = (id) => request(`listings/${id}/`);
export const createListing = (data) => request("listings/", "POST", data);
export const saveListing = (id, data) => request(`listings/${id}/`, "PATCH", data);
export const listingAction = (id, action) => request(`listings/${id}/${action}/`, "POST", {});
export const getCategories = () => request("categories/");
export const getAttributes = (id) => request(`categories/${id}/attributes/`);
export const uploadImage = (id, file) => {
    const data = new FormData();
    data.append("file", file);
    return request(`listings/${id}/images/`, "POST", data);
};
export const saveImageDescription = (id, imageId, description) => request(`listings/${id}/images/${imageId}/`, "PATCH", { description });
export const removeImage = (id, imageId) => request(`listings/${id}/images/${imageId}/`, "DELETE");
export const reorderImages = (id, imageIds) => request(`listings/${id}/images/reorder/`, "PATCH", { image_ids: imageIds });

export function categoryPath(category, categories) {
    const names = [];
    const seen = new Set();
    while (category && !seen.has(category.id)) {
        seen.add(category.id);
        names.unshift(category.name);
        category = categories.find((entry) => entry.id === category.parent);
    }
    return names.join(" › ");
}
