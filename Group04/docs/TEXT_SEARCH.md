# Listing text search

Guests and logged-in users can search through the catalog's search field or the `q` parameter of `GET /api/catalog/listings/`.

## Matching rules

- Split the query into terms using whitespace. Extra spaces, tabs and line breaks are ignored.
- Each term must occur in the title **or** description. Different terms may occur in different fields.
- Combine terms with **AND**: every term must match. Their order does not matter.
- Use Django's `icontains` for case-insensitive substring matching. For example, `cam` matches `camera`. Punctuation is literal, including `%` and `_`.
- An omitted, empty or whitespace-only query applies only the selected filters.
- Queries accept up to 200 characters. Invalid queries return HTTP 400 with an error for `q`.

## Examples

- `camera` matches a title such as **Digital camera**, or a description such as **Includes a camera and a carrying case**.
- `camera case` matches a listing titled **Digital camera** whose description contains **Includes a carrying case**.
- A listing containing only `camera` does not match `camera case`.

All selected filters must also match. Existing visibility restrictions, currency selection, sorting and pagination still apply. The total count includes only matching listings across all pages.

## Run the tests

From the repository root, in PowerShell:

```powershell
.\backend\venv\Scripts\python.exe .\backend\manage.py test tests.catalog.test_text_search
```
