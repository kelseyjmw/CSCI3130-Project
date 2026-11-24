import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getCart, removeFromCart, returnToCart, setCartCurrency, updateQuantity } from "../api/cart";
import "./Cart.css";

export default function Cart() {
    const [cart, setCart] = useState(null);
    const [error, setError] = useState("");

    useEffect(() => {
        let active = true;
        getCart()
            .then((data) => { if (active) setCart(data); })
            .catch((err) => { if (active) setError(err.message || "Failed to fetch the cart"); });
        return () => { active = false; };
    }, []);

    async function run(action) {
        setError("");
        try {
            setCart(await action());
        } catch (err) {
            setError(err.message || "The cart could not be updated");
        }
    }

    return (
        <main className="cart-page">
            <h1>Cart</h1>
            {error && <p className="cart-error" role="alert">{error}</p>}
            {!cart && !error && <p>Loading cart</p>}
            {cart && (
                <label className="cart-currency">
                    Display currency
                    <select
                        value={cart.currency}
                        disabled={cart.checking_out || cart.lines.length === 0}
                        onChange={(event) => run(() => setCartCurrency(event.target.value))}
                    >
                        <option value="CAD">CAD</option>
                        <option value="USD">USD</option>
                    </select>
                </label>
            )}
            {cart && cart.lines.length === 0 && <p>Your cart is empty.</p>}
            {cart && cart.checking_out && <p>Checkout is in progress. Return to the cart before changing it.</p>}
            {cart && cart.lines.length > 0 && (
                <>
                    <ul className="cart-lines">
                        {cart.lines.map((line) => (
                            <li key={`${line.listing_id}-${line.quantity}`}>
                                <Link to={`/listings/${line.listing_id}`}>{line.title || `Listing ${line.listing_id}`}</Link>
                                <form onSubmit={(event) => {
                                    event.preventDefault();
                                    run(() => updateQuantity(line.listing_id, Number(event.target.quantity.value)));
                                }}>
                                    <label>
                                        Qty
                                        <input name="quantity" type="number" min="1" defaultValue={line.quantity} disabled={cart.checking_out} />
                                    </label>
                                    <button type="submit" disabled={cart.checking_out}>Update</button>
                                </form>
                                <span>{cart.currency} {line.line_total}</span>
                                <button type="button" disabled={cart.checking_out} onClick={() => run(() => removeFromCart(line.listing_id))}>Remove</button>
                            </li>
                        ))}
                    </ul>
                    <p className="cart-total">Total {cart.currency} {cart.total}</p>
                    {cart.warnings.map((warning) => <p key={warning}>{warning}</p>)}
                    {cart.checking_out ? (
                        <p className="cart-actions">
                            <button type="button" onClick={() => run(returnToCart)}>Return to cart</button>
                            <Link to="/checkout">Continue checkout</Link>
                        </p>
                    ) : (
                        <p className="cart-actions"><Link to="/checkout">Checkout</Link></p>
                    )}
                </>
            )}
        </main>
    );
}
