import "./NavBar.css";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import UserMenu from "./UserMenu";

export default function NavBar () {
    const { user, loading } = useAuth();

    return (
        <nav className="navbar">
            <Link to="/" className="nav-logo">APP LOGO</Link>
            <Link to="/catalog" className="nav-link">Catalog</Link>
            {!loading && (
        user ? (
            <>
                <Link to="/dashboard" className="nav-link">
                    Dashboard
                </Link>
                <Link to="/my-listings" className="nav-link">My listings</Link>

                <UserMenu />
            </>
            ) : (
                <>
                    <Link to="/login" className="nav-link">
                        Login
                    </Link>

                    <Link to="/register" className="nav-link">
                        Register
                    </Link>
                </>
            )
        )}
        </nav>
    );
}
