import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { searchAccounts } from "../api/adminPanelAccountSearch";
import { setUserRoles } from "../api/roles";
import { setAccountState } from "../api/accountState";
import "./AccountManagement.css";

const ROLE_NAMES = ["Buyer", "Seller", "Moderator", "Administrator"];
const PAGE_SIZE = 10;

function sameRoles(a, b) {
    return [...a].sort().join("|") === [...b].sort().join("|");
}

export default function AccountManagement() {
    const { user } = useAuth();
    const isAdmin = (user?.roles ?? []).some((role) => role.toLowerCase() === "administrator");

    const [searchInput, setSearchInput] = useState("");
    const [search, setSearch] = useState("");
    const [page, setPage] = useState(1);
    const [data, setData] = useState({count: 0, results: []});
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [drafts, setDrafts] = useState({});
    const [reasons, setReasons] = useState({});
    const [notes, setNotes] = useState({});
    const [busyId, setBusyId] = useState(null);

    // Wait 300ms after typing before searching and go back to page 1
    useEffect(() => {
        const timer = setTimeout(() => {
            setSearch(searchInput);
            setPage(1);
        }, 300);
        return () => clearTimeout(timer);
    }, [searchInput]);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        setError("");
        searchAccounts({search, page})
            .then((result) => {
                if (cancelled) {
                    return;
                }
                setData(result);
                setDrafts({});
            })
            .catch ((err) => {
                if (cancelled) {
                    return;
                }
                if (err.status === 404 && page > 1) {
                    setPage(1);
                } else {
                    setError(err.message);
                }
            })
            .finally(() => {
                if (!cancelled) {
                    setLoading(false);
                }
            });
        return () => {
            cancelled = true;
        };
    }, [search, page]);

    function setNote(id, type, text) {
        setNotes((prev) => ({...prev, [id]: text ? {type,text} : undefined}));
    }

    function updateRow(id, changes) {
        setData((prev) => ({
            ...prev,
            results: prev.results.map((row) => (row.id === id ? {...row, ...changes} : row)),
        }));
    }

    function currentRoles(row) {
        return drafts[row.id] ?? row.roles;
    }

    function toggleRole(row, roleName, checked) {
        const roles = currentRoles(row);
        const next = checked
            ? [...new Set([...roles, roleName])]
            : roles.filter((name) => name !== roleName);
        setDrafts((prev) => ({...prev, [row.id]: next}));
        setNote(row.id);
    }

    // Update roles
    async function saveRoles(row) {
        const roles = currentRoles(row);
        setBusyId(row.id);
        setNote(row.id);
        try {
            const updated = await setUserRoles(row.id, roles);
            // Trust the server's roles only if they come back as a list of names.
            const serverRoles =
                Array.isArray(updated?.roles) && updated.roles.every((role) => typeof r === "string")
                    ? updated.roles : roles;
            updateRow(row.id, {roles:serverRoles});
            setDrafts((prev) => {
                const {[row.id]: _removed, ...rest} = prev;
                return rest;
            });
            setNote(row.id, "success", "Roles saved.");
        } catch (err) {
            setNote(row.id, "error", err.message);
        } finally {
            setBusyId(null);
        }
    }

    // Change account state (active/suspended)
    async function changeState(row, nextState) {
        const reason = (reasons[row.id] || "").trim();
        if (!reason) {
            setNote(row.id, "error", "A reason is required.");
            return;
        }
        setBusyId(row.id);
        setNote(row.id);
        try {
            const updated = await setAccountState(row.id, nextState, reason);
            updateRow(row.id, {
                account_state: updated?.account_state ?? nextState,
                suspension_reason:
                nextState === "Suspended" ? (updated?.suspension_reason ?? reason) : "",
            });
            setReasons((prev) => ({...prev, [row.id]: ""}));
            setNote(
                row.id,
                "success",
                nextState === "Suspended" ? "Account suspended." : "Account reactivated."
            );
        } catch (err) {
            setNote(row.id, "error", err.message);
        } finally {
            setBusyId(null);
        }
    }

    const totalPages = Math.max(1, Math.ceil(data.count / PAGE_SIZE));

    return (
        <div id="account-management">
            <h1>Accounts</h1>

            <input
                className="am-search"
                type="search"
                placeholder="Search by email or display name"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
            />

            {error && <p className="am-banner error" role="alert">{error}</p>}
            {loading && <p>Loading...</p>}
            {!loading && !error && data.results.length === 0 && (
                <p className="am-empty">No accounts match your search.</p>
            )}

            <ul className="am-list">
                {data.results.map((row) => {
                    const isSelf = row.id === user?.id;
                    const roles = currentRoles(row);
                    const dirty = !sameRoles(roles, row.roles);
                    const suspended = row.account_state === "Suspended";
                    const busy = busyId === row.id;
                    const note = notes[row.id];

                    return (
                        <li key={row.id} className="am-card">
                            <div className="am-top">
                                <div>
                                    <div className="am-email">{row.email}</div>
                                    <div className="am-meta">
                                        {row.display_name || "No display name"} · joined{" "}
                                        {new Date(row.date_joined).toLocaleDateString()}
                                        {!row.email_verified && " · email not verified"}
                                        {isSelf && " · you"}
                                    </div>
                                </div>
                                <span className={`am-badge ${suspended ? "suspended" : "active"}`}>
                                    {row.account_state}
                                </span>
                            </div>

                            {suspended && row.suspension_reason && (
                                <div className="am-reason">Reason: {row.suspension_reason}</div>
                            )}

                            <div className="am-section">
                                <div className="am-label">Roles</div>
                                {isAdmin ? (
                                    <>
                                        <div className="am-roles">
                                            {ROLE_NAMES.map((name) => (
                                                <label key={name}>
                                                    <input
                                                        type="checkbox"
                                                        checked={roles.includes(name)}
                                                        disabled={isSelf || busy}
                                                        onChange={(e) =>
                                                            toggleRole(row, name, e.target.checked)
                                                        }
                                                    />
                                                    {name}
                                                </label>
                                            ))}
                                        </div>
                                        <button
                                            type="button"
                                            onClick={() => saveRoles(row)}
                                            disabled={!dirty || busy || isSelf}
                                        >
                                            Save roles
                                        </button>
                                    </>
                                ) : (
                                    <div className="am-roles">{row.roles.join(", ") || "None"}</div>
                                )}
                            </div>

                            <div className="am-section">
                                <div className="am-label">Account status</div>
                                <div className="am-state-row">
                                    <input
                                        type="text"
                                        placeholder="Reason (required)"
                                        value={reasons[row.id] || ""}
                                        disabled={isSelf || busy}
                                        onChange={(e) =>
                                            setReasons((prev) => ({
                                                ...prev,
                                                [row.id]: e.target.value,
                                            }))
                                        }
                                    />
                                    {suspended ? (
                                        <button
                                            type="button"
                                            className="am-activate-btn"
                                            disabled={isSelf || busy}
                                            onClick={() => changeState(row, "Active")}
                                        >
                                            Reactivate
                                        </button>
                                    ) : (
                                        <button
                                            type="button"
                                            className="am-danger"
                                            disabled={isSelf || busy}
                                            onClick={() => changeState(row, "Suspended")}
                                        >
                                            Suspend
                                        </button>
                                    )}
                                </div>
                            </div>

                            {isSelf && (
                                <div className="am-meta">
                                    You can't change your own roles or status here.
                                </div>
                            )}
                            {note && (
                                <div
                                    className={`am-banner ${note.type}`}
                                    role={note.type === "error" ? "alert" : "status"}
                                >
                                    {note.text}
                                </div>
                            )}
                        </li>
                    );
                })}
            </ul>

            <div className="am-pagination">
                <button
                    type="button"
                    onClick={() => setPage((p) => p - 1)}
                    disabled={page <= 1 || loading}
                >
                    Previous
                </button>
                <span>
                    Page {page} of {totalPages} · {data.count} account{data.count === 1 ? "" : "s"}
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