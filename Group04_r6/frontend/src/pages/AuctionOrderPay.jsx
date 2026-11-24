import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getAuctionOrder, getAuctionOrderQuote, payAuctionOrder } from "../api/checkout";
import "./Cart.css";

const emptyAddress = {
    full_name: "", line1: "", line2: "", city: "", region: "", postal_code: "", country: "",
};

export default function AuctionOrderPay() {
    const { auctionOrderId } = useParams();
    const [order, setOrder] = useState(null);
    const [quote, setQuote] = useState(null);
    const [address, setAddress] = useState(emptyAddress);
    const [error, setError] = useState("");
    const [message, setMessage] = useState("");
    const [paying, setPaying] = useState(false);

    async function load() {
        const orderData = await getAuctionOrder(auctionOrderId);
        setOrder(orderData);
        if (orderData.payment_status === "Pending") {
            try {
                setQuote(await getAuctionOrderQuote(auctionOrderId));
            } catch {
                // Non-buyers (e.g. seller viewing the order) do not need a buyer quote.
            }
        }
    }

    useEffect(() => {
        let active = true;
        load().catch((err) => { if (active) setError(err.message); });
        return () => { active = false; };
    }, [auctionOrderId]);

    function changeAddress(event) {
        setAddress({ ...address, [event.target.name]: event.target.value });
    }

    async function handlePay(event) {
        event.preventDefault();
        setPaying(true);
        setError("");
        setMessage("");
        try {
            const result = await payAuctionOrder(auctionOrderId, address);
            setMessage(result.already_paid ? "This auction order is already paid." : "Auction payment complete!");
            await load();
        } catch (err) {
            setError(err.message);
        } finally {
            setPaying(false);
        }
    }

    return (
        <main className="cart-page">
            <h1>Auction Order #{auctionOrderId}</h1>
            {error && (
                <div className="cart-error" role="alert">
                    <p>{error}</p>
                    {error.toLowerCase().includes("wallet") && (
                        <p><Link to="/account">Top up your wallet on your Account page</Link> and retry payment.</p>
                    )}
                </div>
            )}
            {message && <p role="status">{message}</p>}
            {!order && !error && <p>Loading auction order...</p>}
            {order && (
                <>
                    <p>Payment status: {order.payment_status}</p>
                    <p>Winning bid: {order.currency} {order.amount}</p>
                    {quote && (
                        <>
                            <p>Subtotal ({quote.buyer_currency}): {quote.buyer_currency} {quote.subtotal}</p>
                            <p>Tax (10%): {quote.buyer_currency} {quote.tax}</p>
                            <p>Delivery: {quote.buyer_currency} {quote.delivery}</p>
                            <p className="cart-total">Wallet deduction: {quote.buyer_currency} {quote.buyer_total}</p>
                        </>
                    )}
                    {order.seller_credit && (
                        <p className="cart-total">Seller credit: {order.seller_currency} {order.seller_credit}</p>
                    )}
                    {order.address ? (
                        <p>
                            Delivery address: {order.address.full_name}, {order.address.line1}
                            {order.address.line2 ? `, ${order.address.line2}` : ""}, {order.address.city}{" "}
                            {order.address.region} {order.address.postal_code}, {order.address.country}
                        </p>
                    ) : (
                        order.seller_credit && <p>The delivery address is hidden until the buyer completes payment.</p>
                    )}
                    {order.payment_status === "Pending" && quote && (
                        <form onSubmit={handlePay} className="cart-form">
                            <h2>Delivery address &amp; payment</h2>
                            {[
                                ["full_name", "Full name"], ["line1", "Address line"], ["line2", "Address line 2"],
                                ["city", "City"], ["region", "Region"], ["postal_code", "Postal code"], ["country", "Country"],
                            ].map(([name, label]) => (
                                <label key={name}>{label}
                                    <input
                                        name={name}
                                        value={address[name]}
                                        required={["line2", "region"].indexOf(name) === -1}
                                        onChange={changeAddress}
                                    />
                                </label>
                            ))}
                            <button type="submit" disabled={paying}>
                                {paying ? "Processing payment..." : `Pay ${quote.buyer_currency} ${quote.buyer_total} with Wallet`}
                            </button>
                        </form>
                    )}
                </>
            )}
        </main>
    );
}
