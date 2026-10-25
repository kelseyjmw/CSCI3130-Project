import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { categoryPath, getAttributes, getCategories, getListings } from "../api/catalog";
import CatalogResults from "../components/CatalogResults";
import "./Catalog.css";

const defaults = {
    q: "",
    category: "",
    currency: "CAD",
    min_price: "",
    max_price: "",
    condition: "",
    ordering: "newest",
};

const conditions = [
    ["new", "New"],
    ["new_no_package", "New, no package"],
    ["refurbished", "Refurbished"],
    ["used_very_good", "Used, very good"],
    ["used_good", "Used, good"],
    ["for_parts", "For parts"],
];

const orderings = [
    ["newest", "Newest"],
    ["price", "Price: low to high"],
    ["-price", "Price: high to low"],
];

const emptyPage = { count: 0, total_pages: 1, results: [] };

// The URL holds the applied filters and the page number, so a reload, the back
// button and the "Back" links on the listing page all return to the same results.
function filtersFromParams(params) {
    const filters = { ...defaults };
    for (const [key, value] of params) {
        if (Object.hasOwn(defaults, key) || key.startsWith("attr.")) {
            filters[key] = value;
        }
    }
    return filters;
}

function paramsFromFilters(filters, page) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
        if (value != null && value !== (defaults[key] ?? "")) {
            params.set(key, value);
        }
    }
    if (page > 1) {
        params.set("page", String(page));
    }
    return params;
}

function sameFilters(a, b) {
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    return [...keys].every((key) => (a[key] ?? "") === (b[key] ?? ""));
}

export default function Catalog() {
    const location = useLocation();
    return <CatalogPage key={location.key} search={location.search} />;
}

function CatalogPage({ search }) {
    const [, setSearchParams] = useSearchParams();
    const applied = useMemo(() => filtersFromParams(new URLSearchParams(search)), [search]);
    const page = Math.max(1, parseInt(new URLSearchParams(search).get("page"), 10) || 1);

    const [data, setData] = useState(emptyPage);
    const [categories, setCategories] = useState([]);
    const [attributes, setAttributes] = useState([]);
    const [form, setForm] = useState(applied);
    const [loading, setLoading] = useState(true);
    const [attributesLoading, setAttributesLoading] = useState(Boolean(applied.category));
    const [errors, setErrors] = useState({});
    const [categoryError, setCategoryError] = useState("");
    const [attributeError, setAttributeError] = useState("");

    useEffect(() => {
        let active = true;
        getCategories()
            .then((tree) => {
                if (active) setCategories(tree);
            })
            .catch((failure) => {
                if (active) setCategoryError(failure.message);
            });
        return () => {
            active = false;
        };
    }, []);

    useEffect(() => {
        let active = true;
        getListings({ ...applied, page })
            .then((result) => {
                if (active) setData(result);
            })
            .catch((failure) => {
                if (!active) return;
                if (failure.status === 404 && page > 1) {
                    // That page no longer exists (listings were removed): go back to page 1.
                    setSearchParams(paramsFromFilters(applied, 1), { replace: true });
                    return;
                }
                setData(emptyPage);
                setErrors(failure.fields || { detail: failure.message });
            })
            .finally(() => {
                if (active) setLoading(false);
            });
        return () => {
            active = false;
        };
    }, [applied, page, setSearchParams]);

    useEffect(() => {
        let active = true;
        (form.category ? getAttributes(form.category) : Promise.resolve([]))
            .then((definitions) => {
                if (active) setAttributes(definitions.filter((attribute) => attribute.filterable));
            })
            .catch((failure) => {
                if (active) setAttributeError(failure.message);
            })
            .finally(() => {
                if (active) setAttributesLoading(false);
            });
        return () => {
            active = false;
        };
    }, [form.category]);

    useEffect(() => {
        window.scrollTo({ top: 0 });
    }, [page]);

    function change(name, value) {
        setForm((current) => ({ ...current, [name]: value }));
    }

    function changeCategory(value) {
        setAttributes([]);
        setAttributeError("");
        setAttributesLoading(Boolean(value));
        setForm((current) => ({
            ...Object.fromEntries(Object.entries(current).filter(([key]) => !key.startsWith("attr."))),
            category: value,
        }));
    }

    // Changing any filter or the sort order returns to page 1.
    function apply(filters) {
        setSearchParams(paramsFromFilters(filters, 1));
    }

    // Sorting applies straight away, together with anything already typed in the form.
    function changeOrdering(value) {
        apply({ ...form, ordering: value });
    }

    function goToPage(number) {
        setSearchParams(paramsFromFilters(applied, number));
    }

    function reset() {
        const cleared = { ...defaults, q: form.q };
        setForm(cleared);
        setAttributes([]);
        setAttributeError("");
        setAttributesLoading(false);
        apply(cleared);
    }

    function error(name) {
        return errors[name] && <span className="catalog-error">{errors[name]}</span>;
    }

    const hasErrors = Object.keys(errors).length > 0;
    const hasChanges = !sameFilters(form, applied);
    return (
        <main className="catalog-page">
            <div className="catalog-heading">
                <div>
                    <h1>Catalog</h1>
                    <p>Explore available listings.</p>
                </div>
                <Link to="/my-listings">My listings</Link>
            </div>

            <form
                className="catalog-filter-panel"
                onSubmit={(event) => {
                    event.preventDefault();
                    apply(form);
                }}
                noValidate
            >
                <div className="catalog-filters catalog-filters-main">
                    <label htmlFor="catalog-q" className="catalog-search">
                        Search listings
                        <input
                            id="catalog-q"
                            name="q"
                            type="search"
                            value={form.q}
                            onChange={(event) => change("q", event.target.value)}
                            placeholder="Search titles and descriptions"
                        />
                        {error("q")}
                    </label>

                    <label htmlFor="catalog-category" className="catalog-field-wide">
                        Category
                        <select
                            id="catalog-category"
                            name="category"
                            value={form.category}
                            onChange={(event) => changeCategory(event.target.value)}
                        >
                            <option value="">All categories</option>
                            {categories
                                .filter((entry) => entry.is_leaf)
                                .map((entry) => (
                                    <option key={entry.id} value={entry.id}>
                                        {categoryPath(entry, categories)}
                                    </option>
                                ))}
                        </select>
                        {error("category")}
                    </label>

                    <label htmlFor="catalog-currency">
                        Currency code
                        <input
                            id="catalog-currency"
                            name="currency"
                            value={form.currency}
                            maxLength={3}
                            placeholder="CAD"
                            onChange={(event) => change("currency", event.target.value.toUpperCase())}
                        />
                        {error("currency")}
                    </label>

                    <label htmlFor="catalog-min-price">
                        Min price ({form.currency || "currency code required"})
                        <input
                            id="catalog-min-price"
                            name="min_price"
                            type="number"
                            min="0"
                            step="0.01"
                            value={form.min_price}
                            placeholder="0.00"
                            onChange={(event) => change("min_price", event.target.value)}
                        />
                        {error("min_price")}
                    </label>

                    <label htmlFor="catalog-max-price">
                        Max price ({form.currency || "currency code required"})
                        <input
                            id="catalog-max-price"
                            name="max_price"
                            type="number"
                            min="0"
                            step="0.01"
                            value={form.max_price}
                            placeholder="No limit"
                            onChange={(event) => change("max_price", event.target.value)}
                        />
                        {error("max_price")}
                    </label>

                    <label htmlFor="catalog-condition">
                        Condition
                        <select
                            id="catalog-condition"
                            name="condition"
                            value={form.condition}
                            onChange={(event) => change("condition", event.target.value)}
                        >
                            <option value="">All conditions</option>
                            {conditions.map(([value, label]) => (
                                <option key={value} value={value}>
                                    {label}
                                </option>
                            ))}
                        </select>
                        {error("condition")}
                    </label>
                </div>

                {attributes.length > 0 && (
                    <fieldset className="catalog-attribute-filters">
                        <legend>Category filters</legend>
                        <div className="catalog-filters">
                            {attributes.map((attribute) => {
                                const name = `attr.${attribute.code}`;
                                const id = `catalog-attr-${attribute.code}`;
                                return (
                                    <label key={attribute.code} htmlFor={id}>
                                        {attribute.name}
                                        {attribute.type === "choice" ? (
                                            <select
                                                id={id}
                                                name={name}
                                                value={form[name] || ""}
                                                onChange={(event) => change(name, event.target.value)}
                                            >
                                                <option value="">Any</option>
                                                {attribute.options.map((option) => (
                                                    <option key={option} value={option}>
                                                        {option}
                                                    </option>
                                                ))}
                                            </select>
                                        ) : (
                                            <input
                                                id={id}
                                                name={name}
                                                type={attribute.type === "number" ? "number" : "text"}
                                                step={attribute.type === "number" ? "any" : undefined}
                                                min={attribute.min_value ?? undefined}
                                                max={attribute.max_value ?? undefined}
                                                placeholder={attribute.type === "number" ? "Exact value" : "Contains text"}
                                                value={form[name] ?? ""}
                                                onChange={(event) => change(name, event.target.value)}
                                            />
                                        )}
                                        {error(name)}
                                    </label>
                                );
                            })}
                        </div>
                    </fieldset>
                )}

                {attributesLoading && <p role="status">Loading category filters…</p>}

                {(categoryError || attributeError) && (
                    <p role="alert" className="catalog-error">
                        {categoryError || attributeError}
                    </p>
                )}

                <div className="catalog-actions">
                    <button
                        type="submit"
                        disabled={loading || attributesLoading || Boolean(attributeError) || (!hasChanges && !hasErrors)}
                    >
                        Apply filters
                    </button>
                    <button type="button" className="catalog-button-secondary" onClick={reset}>
                        Clear filters
                    </button>
                </div>
            </form>

            {hasErrors && (
                <p role="alert" className="catalog-error">
                    {Object.values(errors).join(" ")}
                </p>
            )}

            <CatalogResults data={data} loading={loading} hasError={hasErrors} page={page} onPageChange={goToPage} from={search}>
                <label htmlFor="catalog-ordering" className="catalog-sort">
                    Sort by
                    <select id="catalog-ordering" name="ordering" value={applied.ordering} onChange={(event) => changeOrdering(event.target.value)}>
                        {orderings.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                </label>
            </CatalogResults>
        </main>
    );
}
