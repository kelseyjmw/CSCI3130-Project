import ResultCard from "./ResultCard";

export default function CatalogResults({ data, loading, hasError, page, onPageChange, from, children }) {
    if (hasError) return null;
    return <section aria-label="Search results">
        <div className="catalog-toolbar">
            <p className="catalog-count" role="status">{loading ? "Loading listings…" : `${data.count} listing${data.count === 1 ? "" : "s"} found`}</p>
            {children}
        </div>
        {!loading && (data.count === 0 ? <p className="catalog-empty">No listings match. Try changing your search or clearing filters.</p>
            : <div className="catalog-grid">{data.results.map((listing) => <ResultCard key={listing.id} {...listing} from={from} />)}</div>)}
        {!loading && (data.previous || data.next) && <nav className="catalog-pagination" aria-label="Results pages">
            <button type="button" disabled={!data.previous} onClick={() => onPageChange(page - 1)}>Previous</button>
            <span>Page {page}{data.total_pages != null && ` of ${data.total_pages}`}</span>
            <button type="button" disabled={!data.next} onClick={() => onPageChange(page + 1)}>Next</button>
        </nav>}
    </section>;
}
