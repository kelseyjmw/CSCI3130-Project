import { useEffect, useMemo, useState } from "react";

const API_URL = "http://127.0.0.1:8000/api/accounts";

export default function ApplicationForm({ onSubmitted }) {
  const [sellerType, setSellerType] = useState("person");
  const [company, setCompany] = useState({
    company_name: "",
    address: "",
    tax_number: "",
  });
  const [idFile, setIdFile] = useState(null);
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");

  const previewUrl = useMemo(
    () => (idFile ? URL.createObjectURL(idFile) : null),
    [idFile],
  );

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setErrors({});
    setMessage("");

    const formData = new FormData();
    formData.append("applicant_type", sellerType);
    if (sellerType === "company") {
      formData.append("company_name", company.company_name);
      formData.append("company_address", company.address);
      formData.append("company_tax_number", company.tax_number);
    }
    if (idFile) formData.append("identity_document_image", idFile);

    try {
      const csrfResponse = await fetch(`${API_URL}/csrf/`, {
        credentials: "include",
      });
      if (!csrfResponse.ok) {
        throw new Error("Could not initialize secure form submission.");
      }
      const { csrfToken } = await csrfResponse.json();

      const response = await fetch(`${API_URL}/seller-applications/`, {
        method: "POST",
        body: formData,
        credentials: "include",
        headers: { "X-CSRFToken": csrfToken },
      });
      const responseData = await response.json();

      if (!response.ok) {
        setErrors(responseData);
        return;
      }
      setMessage(responseData.detail);
      onSubmitted?.();
    } catch (error) {
      setErrors({ detail: error.message || "Application submission failed." });
    } finally {
      setSubmitting(false);
    }
  }

  function errorMessage(field) {
    const value = errors[field];
    return Array.isArray(value) ? value.join(" ") : value;
  }

  return (
    <div id="app-form">
      <h1>Seller application</h1>
      <form onSubmit={handleSubmit}>
        <div className="form-section radio-section" style={{ marginBottom: '10px' }}>
          <label>
            <input
              type="radio"
              name="applicant_type"
              value="person"
              checked={sellerType === "person"}
              onChange={() => setSellerType("person")}
            />
            Person
          </label>
          <label>
            <input
              type="radio"
              name="applicant_type"
              value="company"
              checked={sellerType === "company"}
              onChange={() => setSellerType("company")}
            />
            Company
          </label>
        </div>

        {sellerType === "company" && (
          <>
            {[
              ["company_name", "company_name", "Company name"],
              ["address", "company_address", "Company address"],
              ["tax_number", "company_tax_number", "Tax number"],
            ].map(([field, apiField, label]) => (
              <div className="form-section" key={field}>
                <label htmlFor={field}>{label}</label>
                <input
                  id={field}
                  value={company[field]}
                  onChange={(event) =>
                    setCompany({ ...company, [field]: event.target.value })
                  }
                  required
                />
                {errorMessage(apiField) && <span>{errorMessage(apiField)}</span>}
              </div>
            ))}
          </>
        )}

        <div className="form-section">
          <label htmlFor="identity_document_image">Identity document image</label>
          <input
            id="identity_document_image"
            type="file"
            accept="image/jpeg,image/png"
            onChange={(event) => setIdFile(event.target.files[0] ?? null)}
            required
          />
          {errorMessage("identity_document_image") && (
            <span>{errorMessage("identity_document_image")}</span>
          )}
        </div>

        {previewUrl && <img src={previewUrl} alt="Identity document preview" width={200} />}
        {errorMessage("detail") && <p role="alert">{errorMessage("detail")}</p>}
        {errorMessage("non_field_errors") && (
          <p role="alert">{errorMessage("non_field_errors")}</p>
        )}
        {message && <p role="status">{message}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Submitting..." : "Submit application"}
        </button>
      </form>
    </div>
  );
}