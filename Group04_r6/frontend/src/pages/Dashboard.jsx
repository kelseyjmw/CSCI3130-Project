import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

function Dashboard() {

    const { user } = useAuth();
    const navigate = useNavigate();
    const [orderId, setOrderId] = useState("");

    function openOrder(event) {
        event.preventDefault();
        const trimmed = orderId.trim();
        if (trimmed) navigate(`/orders/${trimmed}`);
    }

    return (
        <div>
            <h1>Welcome to the Dashboard!</h1>
            <p>Welcome, {user.email}!</p>
            {user.account_state === "Suspended" && (
                <p style={{ color: "red" }}>
                    Your account is suspended.
                    <br />
                    Suspension reason: {user.suspension_reason}
                </p>
            )}
            <p>
                Account state: {user.account_state || "Active"}
            </p>

            {user.suspended_at && (
                <p>Suspended at: {new Date(user.suspended_at).toLocaleString()}</p>
            )}

            {user.previous_login ? (
                <p>
                    Previous login:{" "}
                    {new Date(user.previous_login).toLocaleString()}
                </p>
            ) : (
                <p>No previous successful login.</p>
            )}

            <section className="page-card" style={{ marginTop: "1.5rem" }}>
                <h2>Orders &amp; Wallet</h2>
                <p>
                    <Link to="/account">Manage Wallet &amp; Transactions</Link>{" | "}
                    <Link to="/cart">View Cart</Link>{" | "}
                    <Link to="/notifications">Auction Notifications &amp; Orders</Link>
                </p>
                <form onSubmit={openOrder} style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginTop: "0.75rem" }}>
                    <label htmlFor="dashboard-order-id">Order #</label>
                    <input
                        id="dashboard-order-id"
                        type="number"
                        min="1"
                        placeholder="Enter order ID"
                        value={orderId}
                        onChange={(e) => setOrderId(e.target.value)}
                    />
                    <button type="submit">View Order</button>
                </form>
            </section>

        </div>
    );
}

export default Dashboard;
