import { useEffect, useState } from "react";
import { getAuditLog } from "../api/auditLog";
import "./AuditLog.css";

const PAGE_SIZE = 25;

function formatUtc(timestamp) {
    return new Date(timestamp).toISOString().replace("T", " ").slice(0, 19) + " UTC";
}

function label(value) {
    return value.replaceAll("_", " ");
}

function accountId(id) {
    return id == null ? <span className="al-muted">unknown</span> : `Account #${id}`;
}

export default function AuditLog() {
    const [page, setPage] = useState(1);
    const [data, setData] = useState({ count: 0, results: [] });
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        setError("");
        getAuditLog(page)
            .then((result) => {
                if (!cancelled) setData(result);
            })
            .catch((err) => {
                if (cancelled) return;
                if (err.status === 404 && page > 1) setPage(1);
                else setError(err.message);
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [page]);

    const totalPages = Math.max(1, Math.ceil(data.count / PAGE_SIZE));

    return (
        <div id="audit-log">
            <h1>Audit log</h1>
            <p className="al-muted">Newest first. All times are UTC.</p>

            {error && <p className="al-banner error" role="alert">{error}</p>}
            {loading && <p>Loading...</p>}
            {!loading && !error && data.results.length === 0 && (
                <p className="al-empty">No audit entries yet.</p>
            )}

            {data.results.length > 0 && (
                <div className="al-table-wrap">
                    <table className="al-table">
                        <thead>
                            <tr>
                                <th>Time (UTC)</th>
                                <th>Action</th>
                                <th>Result</th>
                                <th>Actor</th>
                                <th>Target</th>
                                <th>Reason</th>
                            </tr>
                        </thead>
                        <tbody>
                            {data.results.map((entry) => (
                                <tr key={entry.id}>
                                    <td className="al-nowrap">{formatUtc(entry.timestamp)}</td>
                                    <td>{label(entry.action)}</td>
                                    <td>
                                        <span className={`al-badge ${entry.result}`}>{entry.result}</span>
                                    </td>
                                    <td>{accountId(entry.actor)}</td>
                                    <td>{accountId(entry.target)}</td>
                                    <td className="al-reason">{entry.reason || "—"}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            <div className="al-pagination">
                <button
                    type="button"
                    onClick={() => setPage((p) => p - 1)}
                    disabled={page <= 1 || loading}
                >
                    Previous
                </button>
                <span>
                    Page {page} of {totalPages} · {data.count} entr{data.count === 1 ? "y" : "ies"}
                </span>
                <button
                    type="button"
                    onClick={() => setPage((p) => p + 1)}
                    disabled={page >= totalPages || loading}
                >
                    Next
                </button>
            </div>
        </div>
    );
}