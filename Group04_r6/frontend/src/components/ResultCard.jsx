import { Link } from "react-router-dom";

export default function ResultCard({ id, title, primary_image, price, currency, listing_type = "fixed_price", from = "" }) {
    return (
        <Link to={`/listings/${id}`} state={{ from }} className="catalog-card">
            {primary_image ? (
                <img src={primary_image} alt={title}/>
            ) : (
                <div className="catalog-card-placeholder" role="img" aria-label="No image available">No image</div>
            )}
            <div>
                <h2>{title}</h2>
                <p className="catalog-price">{currency} {price}</p>
                {listing_type === "auction" && <p>Auction</p>}
            </div>
        </Link>
    );
}
