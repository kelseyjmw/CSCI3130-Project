import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

function Dashboard() {

    const { user } = useAuth();
    const navigate = useNavigate();

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

        </div>
    );
}

export default Dashboard;