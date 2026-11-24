export default function OrderSummary({ order }) {
    return (
        <>
            <p>Order {order.order_id}</p>
            <p>Payment status: {order.payment_status}</p>
            <ul className="cart-lines">
                {order.lines.map((line) => (
                    <li key={`${line.listing_id}-${line.quantity}`}>
                        <span>Listing {line.listing_id}</span>
                        <span>Qty {line.quantity}</span>
                        <span>{line.currency} {line.unit_price}</span>
                    </li>
                ))}
            </ul>
            {order.display_subtotal && <p>Subtotal {order.display_currency} {order.display_subtotal}</p>}
            {order.display_tax && <p>Tax {order.display_currency} {order.display_tax}</p>}
            {order.display_delivery && <p>Delivery {order.display_currency} {order.display_delivery}</p>}
            {order.display_total && <p>Display total {order.display_currency} {order.display_total}</p>}
            {order.buyer_total && <p className="cart-total">Wallet charge {order.buyer_currency} {order.buyer_total}</p>}
            {order.seller_shares && order.seller_shares.map((share) => (
                <p key={share.seller_id}>Seller {share.seller_id} receives {share.credit_currency} {share.credit}</p>
            ))}
            {order.share && <p className="cart-total">Your share {order.share.credit_currency} {order.share.credit}</p>}
            {order.address ? (
                <p>{order.address.full_name}, {order.address.line1}{order.address.line2 ? `, ${order.address.line2}` : ""}, {order.address.city} {order.address.region} {order.address.postal_code}, {order.address.country}</p>
            ) : order.share ? <p>The delivery address is hidden until this order is paid.</p> : null}
        </>
    );
}
