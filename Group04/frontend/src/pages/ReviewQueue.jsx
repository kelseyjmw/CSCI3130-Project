import { useCallback, useEffect, useState } from "react";
import "./ReviewQueue.css"

const API_URL = "http://127.0.0.1:8000/api/accounts";

export default function ReviewQueue() {
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/seller-applications/pending/`, {
        credentials: "include",
      });
      if (response.status === 403) {
        throw new Error("You do not have permission to review applications.");
      }
      if (!response.ok) throw new Error("Could not load applications.");
      setApplications(await response.json());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function approve(application) {
    if (!window.confirm(`Approve ${application.applicant_email} as a seller?`)) return;
    setBusyId(application.id);
    setError("");
    setMessage("");
    try {
      const csrfResponse = await fetch(`${API_URL}/csrf/`, { credentials: "include" });
      const { csrfToken } = await csrfResponse.json();

      const response = await fetch(
        `${API_URL}/seller-applications/${application.id}/approve/`,
        {
          method: "POST",
          credentials: "include",
          headers: { "X-CSRFToken": csrfToken },
        },
      );
      const data = await response.json();
      if (!response.ok) {
        setError(data.detail || "Approval failed.");
        if (response.status === 409) load(); // someone else already handled it
        return;
      }
      setMessage(data.detail);
      setApplications((current) => current.filter((a) => a.id !== application.id));
    } catch (err) {
      setError(err.message || "Approval failed.");
    } finally {
      setBusyId(null);
    }
  }

  async function reject(application) {
    const reason = window.prompt(
        `Reason for rejecting ${application.applicant_email}:`
    );

    if (reason === null) {
        return;
    }
    if (!reason.trim()) {
        setError("A reason is required to reject an application.");
        return;
    }
    setBusyId(application.id);
    setError("");
    setMessage("");

    try {
        const csrfResponse = await fetch(`${API_URL}/csrf/`, { credentials: "include" });
        const { csrfToken } = await csrfResponse.json();

        const response = await fetch(
            `${API_URL}/seller-applications/${application.id}/reject/`,
            {
                method: "POST",
                credentials: "include",
                headers: {
                    "X-CSRFToken": csrfToken,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ reason: reason.trim() }),
            },
        );
        const data = await response.json();
        if (!response.ok) {
            setError(data.detail || "Rejection failed.");
            if (response.status === 409) {
                load();
            }
            return;
        }
        setMessage(data.detail);
        setApplications((current) => current.filter((a) => a.id !== application.id));
    } catch (err) {
        setError(err.message || "Rejection failed.");
    } finally {
        setBusyId(null);
    }
  }

  return (
    <div id="review-queue">
      <h1>Pending Seller Applications</h1>

      {error && <p className="rq-banner error" role="alert">{error}</p>}
      {message && <p className="rq-banner success" role="status">{message}</p>}
      {loading && <p>Loading...</p>}

      {!loading && !error && applications.length === 0 && (
        <p className="rq-empty">No pending applications. You're all caught up.</p>
      )}

      <ul className="rq-list">
        {applications.map((a) => (
          <li key={a.id} className="rq-card">
            <div className="rq-top">
              <span className="rq-email">{a.applicant_email}</span>
              <span className={`rq-badge ${a.applicant_type}`}>{a.applicant_type}</span>
            </div>
            <div className="rq-meta">
              Submitted {new Date(a.created_at).toLocaleString()}
            </div>

            {a.applicant_type === "company" && (
              <dl className="rq-details">
                <dt>Company</dt>
                <dd>{a.company_name}</dd>
                <dt>Address</dt>
                <dd>{a.company_address}</dd>
                <dt>Tax number</dt>
                <dd>{a.company_tax_number}</dd>
              </dl>
            )}

            <div className="rq-actions">
              <a
                className="rq-doc"
                href={a.document_url ?? a.identity_document_image}
                target="_blank"
                rel="noreferrer"
              >
                View identity document ↗
              </a>
              <div className="rq-buttons">
                <button
                  className="rq-btn reject"
                  onClick={() => reject(a)}
                  disabled={busyId === a.id}
                >
                  Reject
                </button>
                <button
                  className="rq-btn approve"
                  onClick={() => approve(a)}
                  disabled={busyId === a.id}
                >
                  {busyId === a.id ? "Working..." : "Approve"}
                </button>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}