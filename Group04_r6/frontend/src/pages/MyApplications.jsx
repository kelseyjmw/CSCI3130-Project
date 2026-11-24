import { useEffect, useState } from "react";
import "./MyApplications.css";

const API_URL = "http://127.0.0.1:8000/api/accounts";

function ReapplyNote({ availableAt }) {
  const when = new Date(availableAt);
  const waiting = when > new Date();
  return (
    <div className={`ma-reapply ${waiting ? "waiting" : "ready"}`}>
      {waiting
        ? `You can reapply after ${when.toLocaleString()}`
        : "You can reapply now"}
    </div>
  );
}

function Row({ a, showReapply }) {
  return (
    <li className="ma-card">
      <div className="ma-top">
        <span className="ma-title">
          {a.applicant_type === "company" ? a.company_name : "Personal application"}
        </span>
        <span className={`ma-badge ${a.status}`}>{a.status}</span>
      </div>
      <div className="ma-meta">
        <span>Submitted {new Date(a.created_at).toLocaleString()}</span>
        {a.reviewed_at && (
          <span>Reviewed {new Date(a.reviewed_at).toLocaleString()}</span>
        )}
      </div>
      {a.review_reason && (
        <div className="ma-reason">
          <strong>Reason</strong>
          {a.review_reason}
        </div>
      )}
      {showReapply && a.reapply_available_at && (
        <ReapplyNote availableAt={a.reapply_available_at} />
      )}
    </li>
  );
}

function Section({ title, items, emptyText, latestRejectedId }) {
  return (
    <>
      <h2>{title}</h2>
      {items.length === 0 ? (
        <p className="ma-empty">{emptyText}</p>
      ) : (
        <ul className="ma-list">
          {items.map((a) => (
            <Row key={a.id} a={a} showReapply={a.id === latestRejectedId} />
          ))}
        </ul>
      )}
    </>
  );
}

export default function MyApplications({ showPending, refreshKey, onLoaded }) {
  const [applications, setApplications] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_URL}/seller-applications/mine/`, { credentials: "include" })
      .then((r) => {
        if (!r.ok) throw new Error("Could not load your applications.");
        return r.json();
      })
      .then((data) => {
        const list = Array.isArray(data) ? data : data.results;
        setApplications(list);
        onLoaded?.(list);
      })
      .catch((err) => setError(err.message));
  }, [refreshKey]);

  const pending = applications.filter((a) => a.status === "pending");
  const past = applications.filter((a) => a.status !== "pending");

  const latestRejectedId = applications
    .filter((a) => a.status === "rejected" && a.reviewed_at)
    .sort((x, y) => new Date(y.reviewed_at) - new Date(x.reviewed_at))[0]?.id;

  return (
    <div id="my-applications">
      {error && <p className="ma-banner" role="alert">{error}</p>}
      {showPending && (
        <Section
          title="My pending applications"
          items={pending}
          emptyText="You have no pending applications."
        />
      )}
      <Section
        title="Past applications"
        items={past}
        emptyText="No past applications yet."
        latestRejectedId={latestRejectedId}
      />
    </div>
  );
}