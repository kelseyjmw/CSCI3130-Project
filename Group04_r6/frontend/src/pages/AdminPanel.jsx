import { useSearchParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import ReviewQueue from "./ReviewQueue";
import AuditLog from "../components/AuditLog";
import AccountManagement from "../components/AccountManagement";
import "./AdminPanel.css";

const SECTIONS = [
    {key: "accounts", label: "Accounts", component: AccountManagement, adminOnly: false},
    {key: "applications", label: "Review Applications", component: ReviewQueue, adminOnly: false},
    {key: "audit", label: "Audit Log", component: AuditLog, adminOnly: true},
];

export default function AdminPanel() {
    const { user } = useAuth();
    const [searchParams, setSearchParams] = useSearchParams();

    const roleNames = (user.roles ?? []).map((role) => role.toLowerCase());
    const isAdmin = roleNames.includes("administrator");
    const isReviewer = isAdmin || roleNames.includes("moderator");

    if (!isReviewer) {
        return (
            <div className="page">
                <h1>Admin Panel</h1>
                <p role="alert" className="page-card">
                    You do not have permission to view this page.
                </p>
            </div>
        );
    }

    // Moderators only see sections that are not admin only
    const visibleSections = SECTIONS.filter((section) => !section.adminOnly || isAdmin);

    const requested = searchParams.get("section");
    const active = visibleSections.find((section) => section.key === requested) ?? visibleSections[0];
    const ActiveSection = active.component;

    return (
        <div className="admin-layout">
            <aside className="admin-sidebar">
                <h2 className="admin-sidebar-title">Admin Panel</h2>
                <nav>
                    <ul>
                        {visibleSections.map((section) => (
                            <li key={section.key}>
                                <button
                                    className={`admin-sidebar-item ${section.key === active.key ? "active" : ""}`}
                                    onClick={() => setSearchParams({section: section.key})}
                                    aria-current={section.key === active.key ? "page" : undefined}
                                >
                                    {section.label}
                                </button>
                            </li>
                        ))}
                    </ul>
                </nav>
            </aside>

            <main className="admin-content">
                <ActiveSection />
            </main>
        </div>
    );
}