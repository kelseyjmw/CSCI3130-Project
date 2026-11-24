import { useEffect, useState } from "react";
import ApplicationForm from "./ApplicationForm";
import MyApplications from "./MyApplications";
import ReviewQueue from "./ReviewQueue";

const API_URL = "http://127.0.0.1:8000/api/accounts";

export default function Applications() {
  const [roles, setRoles] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    fetch(`${API_URL}/me/`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((me) => setRoles(me.roles))
      .catch(() => setRoles([]));
  }, []);

  if (roles === null) return <p>Loading...</p>;

  const isBuyer = roles.includes("Buyer");
  const isSeller = roles.includes("Seller");

  // Sellers keep the Buyer role, so exclude them from applying again.
  const canApply = isBuyer && !isSeller;
  const showMine = isBuyer || isSeller;

  return (
    <div>
      {canApply && <ApplicationForm onSubmitted={() => setRefreshKey((k) => k + 1)} />}
      {showMine && <MyApplications showPending={canApply} refreshKey={refreshKey} />}
    </div>
  );
}