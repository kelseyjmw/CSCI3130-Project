import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { confirmCheckout, getCheckoutReview, payOrder, returnToCart, saveDeliveryAddress, startCheckout } from "../api/checkout";
import { getCart } from "../api/cart";
import { useAuth } from "../context/AuthContext";
import "./Cart.css";

const emptyAddress = {
    full_name: "", line1: "", line2: "", city: "", region: "", postal_code: "", country: "",
};

export default function Checkout() {
    const { user, loading } = useAuth();
    const navigate = useNavigate();
    const [cart, setCart] = useState(null);
    const [review, setReview] = useState(null);
    const [email, setEmail] = useState("");
    const [address, setAddress] = useState(emptyAddress);
    const [token, setToken] = useState("");
    const [message, setMessage] = useState("");
    const [error, setError] = useState("");
    const [paying, setPaying] = useState(false);

    async function load() {
        const [cartData, reviewResult] = await Promise.all([
            getCart(),
            getCheckoutReview().catch((err) => {
                if (err.response?.status === 400) return null;
                throw err;
            }),
        ]);
        setCart(cartData);
        setReview(reviewResult);
    }

    useEffect(() => {
        let active = true;
        load().catch((err) => { if (active) setError(err.message); });
        return () => { active = false; };
    }, []);

    function changeAddress(event) {
        setAddress({ ...address, [event.target.name]: event.target.value });
    }

    async function begin(event) {
        event.preventDefault();
        setError("");
        setMessage("");
        try {
            const started = await startCheckout(user ? "" : email);
            if (started.guest_access_token) setToken(started.guest_access_token);
            setReview(started);
            setCart(await getCart());
        } catch (err) {
            setError(err.message);
        }
    }

    async function saveAddress(event) {
        event.preventDefault();
        setError("");
        try {
            await saveDeliveryAddress(address);
            setMessage("Delivery address saved on this order.");
        } catch (err) {
            setError(err.message);
        }
    }

    async function confirm() {
        setError("");
        try {
            setReview(await confirmCheckout());
            setMessage("Amounts confirmed.");
        } catch (err) {
            setError(err.message);
        }
    }

    async function handleReturnToCart() {
        setError("");
        try {
            await returnToCart();
            navigate("/cart");
        } catch (err) {
            setError(err.message);
        }
    }

    async function handlePay() {
        if (!review?.order_id) return;
        setPaying(true);
        setError("");
        setMessage("");
        try {
            const result = await payOrder(review.order_id);
            setMessage(result.already_paid ? "This order is already paid." : "Payment complete. Your cart has been cleared.");
            if (token) {
                navigate(`/orders/guest/${token}`);
            } else {
                navigate(`/orders/${review.order_id}`);
            }
        } catch (err) {
            setError(err.message);
        } finally {
            setPaying(false);
        }
    }

    if (loading || (!cart && !error)) return <main className="cart-page"><h1>Checkout</h1><p>Loading checkout</p></main>;

    return (
        <main className="cart-page">
            <h1>Checkout</h1>
            {error && (
                <div className="cart-error" role="alert">
                    <p>{error}</p>
                    {error.toLowerCase().includes("wallet") && (
                        <p><Link to="/account">Top up your wallet on your Account page</Link> and retry payment.</p>
                    )}
                </div>
            )}
            {message && <p role="status">{message}</p>}
            {cart && cart.lines.length === 0 && <p>Your cart is empty. <Link to="/catalog">Browse the catalog</Link></p>}
            {cart && cart.lines.length > 0 && (
                <ul className="cart-lines">
                    {cart.lines.map((line) => (
                        <li key={line.listing_id}>
                            <span>{line.title || `Listing ${line.listing_id}`}</span>
                            <span>Qty {line.quantity}</span>
                            <span>{cart.currency} {line.line_total}</span>
                        </li>
                    ))}
                </ul>
            )}
            {!review && cart && cart.lines.length > 0 && (
                <form onSubmit={begin} className="cart-form">
                    {!user && (
                        <label>Email address
                            <input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
                        </label>
                    )}
                    <button type="submit">Start checkout</button>
                </form>
            )}
            {review && (
                <>
                    <p>Subtotal {review.display_currency} {review.display_subtotal}</p>
                    <p>Tax {review.display_currency} {review.display_tax}</p>
                    <p>Delivery {review.display_currency} {review.display_delivery}</p>
                    <p>Display total {review.display_currency} {review.display_total}</p>
                    <p className="cart-total">Wallet charge {review.buyer_currency} {review.buyer_total}</p>
                    {review.needs_confirmation && <p>The total changed. Confirm the new amounts before continuing.</p>}
                    <form onSubmit={saveAddress} className="cart-form">
                        <h2>Delivery address</h2>
                        {[
                            ["full_name", "Full name"], ["line1", "Address line"], ["line2", "Address line 2"],
                            ["city", "City"], ["region", "Region"], ["postal_code", "Postal code"], ["country", "Country"],
                        ].map(([name, label]) => (
                            <label key={name}>{label}
                                <input name={name} value={address[name]} required={["line2", "region"].indexOf(name) === -1} onChange={changeAddress} />
                            </label>
                        ))}
                        <button type="submit">Save address</button>
                    </form>
                    <p className="cart-actions">
                        <button type="button" onClick={confirm}>{review.needs_confirmation ? "Confirm new amounts" : "Confirm these amounts"}</button>
                        {review.order_id && (
                            <button type="button" disabled={paying} onClick={handlePay}>
                                {paying ? "Processing payment..." : `Pay ${review.buyer_currency} ${review.buyer_total} with Wallet`}
                            </button>
                        )}
                        <button type="button" onClick={handleReturnToCart}>Return to cart</button>
                        {review.order_id && <Link to={`/orders/${review.order_id}`}>View order</Link>}
                    </p>
                    {token && (
                        <p>Guest order link: <Link to={`/orders/guest/${token}`}>/orders/guest/{token}</Link>. Save it. The email and order number alone do not open the order.</p>
                    )}
                </>
            )}
        </main>
    );
}
