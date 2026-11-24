import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import "./UserMenu.css";

export default function UserMenu() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();
    const [open, setOpen] = useState(false);
    const menuRef = useRef(null);

    useEffect(() => {
        if (!open) {
            return;
        }
        function onClick(e) {
            if (menuRef.current && !menuRef.current.contains(e.target)) {
                setOpen(false);
            }
        }
        function onKey(e) {
            if (e.key === "Escape") {
                setOpen(false);
            }
        }
        document.addEventListener("mousedown", onClick);
        document.addEventListener("keydown", onKey);
        return () => {
            document.removeEventListener("mousedown", onClick);
            document.removeEventListener("keydown", onKey)
        };
    }, [open]);

    async function handleLogout() {
        setOpen(false);
        try {
            await logout();
            navigate("/login");
        } catch (error) {
            console.error(error);
        }
    }

    const isModerator = (user.roles ?? []).some((role) =>
    ["moderator", "administrator"].includes(role.toLowerCase())
    );

    return (
        <div className="user-menu" ref={menuRef}>
        <button
            className="user-menu-trigger"
            onClick={() => setOpen((o) => !o)}
            aria-haspopup="menu"
            aria-expanded={open}
        >
            {user.email} <span className="user-menu-caret">{open ? "▴" : "▾"}</span>
        </button>

        {open && (
            <ul className="user-menu-dropdown" role="menu">
            <li role="none">
                <Link role="menuitem" to="/profile" onClick={() => setOpen(false)}>
                Profile
                </Link>
            </li>
            <li role="none">
                <Link role="menuitem" to="/account" onClick={() => setOpen(false)}>
                Account
                </Link>
            </li>
            <li role="none">
                <Link role="menuitem" to="/applications" onClick={() => setOpen(false)}>
                Applications
                </Link>
            </li>
            {isModerator && (
                <li role="none">
                <Link role="menuitem" to="/admin-panel" onClick={() => setOpen(false)}>
                    Admin panel
                </Link>
                </li>
            )}
            <li role="separator" className="user-menu-divider" />
            <li role="none">
                <button role="menuitem" onClick={handleLogout}>
                Logout
                </button>
            </li>
            </ul>
        )}
        </div>
    );
}