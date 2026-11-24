import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getGuestOrder, payOrder } from "../api/checkout";
import OrderSummary from "../components/OrderSummary";
import "./Cart.css";

export default function GuestOrder() {
    const { token } = useParams();
    const [order, setOrder] = useState(null);
    const [error, setError] = useState("");
    const [message, setMessage] = useState("");
    const [paying, setPaying] = useState(false);

    useEffect(() => {
        let active = true;
        getGuestOrder(token)
            .then((data) => { if (active) setOrder(data); })
            .catch((err) => { if (active) setError(err.message); });
        return () => { active = false; };
    }, [token]);

    async function handlePay() {
        if (!order?.order_id) return;
        setPaying(true);
        setError("");
        setMessage("");
        try {
            const result = await payOrder(order.order_id);
            setMessage(result.already_paid ? "Payment is already complete." : "Payment successful! Order marked Paid.");
            setOrder(await getGuestOrder(token));
        } catch (err) {
            setError(err.message);
        } finally {
            setPaying(false);
        }
    }

    return (
        <main className="cart-page">
            <h1>Guest order</h1>
            {error && (
                <div className="cart-error" role="alert">
                    <p>{error}</p>
                    {error.toLowerCase().includes("wallet") && (
                        <p><Link to="/account">Top up your guest wallet</Link> and retry payment.</p>
                    )}
                </div>
            )}
            {message && <p role="status">{message}</p>}
            {!order && !error && <p>Loading order</p>}
            {order && (
                <>
                    <OrderSummary order={order} />
                    {order.payment_status === "Pending" && order.buyer_total && (
                        <p className="cart-actions">
                            <button type="button" disabled={paying} onClick={handlePay}>
                                {paying ? "Processing payment..." : `Pay ${order.buyer_currency} ${order.buyer_total} with Wallet`}
                            </button>
                        </p>
                    )}
                </>
            )}
        </main>
    );
}
