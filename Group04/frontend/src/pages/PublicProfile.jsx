import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import "./Pages.css";

const API_URL = "http://127.0.0.1:8000/api/accounts";

export default function PublicProfile() {
    const { userId } = useParams();
    const [profile, setProfile] = useState(null);
    const [error, setError] = useState("");

    useEffect(() => {
        setProfile(null);
        setError("");
        fetch(`${API_URL}/profiles/${userId}`).then((response) => {
            if (response.status === 404) {
                throw new Error("This profile does not exist.");
            }
            if (!response.ok) {
                throw new Error("Could not load this profile.");
            }
            return response.json();
        })
        .then(setProfile)
        .catch((err) => setError(err.message));
    }, [userId]);

    if (error) {
        return (
            <div className="page">
                <p role="alert" className="page-card">{error}</p>
            </div>
        );
    }
    if (!profile) {
        return <p>Loading...</p>;
    }

    return (
        <div className="page">
            <h1>{profile.display_name}</h1>
            <div className="page-card">
                <dl className="page-details">
                    <dt>Member Since</dt>
                    <dd>{new Date(profile.member_since).toLocaleDateString()}</dd>
                    <dt>Rating</dt>
                    <dd>{profile.rating == null ? "No ratings yet" : `${profile.rating} / 5`}</dd>
                </dl>
            </div>
        </div>
    );
}