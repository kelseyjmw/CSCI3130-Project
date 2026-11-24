# Release 6: Cart, Checkout, and Payments — Design Decisions

## 1. Tax Rate, Delivery-Charge Rule, and Rounding Rule
- **Simulated Tax Rate**: A static **10%** (`0.10`) tax is applied to each seller's item subtotal (listing prices are tax-exclusive).
- **Delivery-Charge Rule**: A flat **5.00** unit delivery fee (in the buyer's wallet currency) is charged **per seller** in the order. Delivery charges are not taxed.
- **Rounding & Exact Decimal Calculation**: All monetary calculations are performed server-side using Python `Decimal` arithmetic (`backend/commerce/pricing.py`) and rounded to two decimal places (`0.01`) using `ROUND_HALF_UP`. For multi-seller orders, each seller's share (`item subtotal + 10% tax + 5.00 delivery`) is rounded in the buyer's wallet currency and summed so the buyer's total charge equals the exact sum of seller shares. Each seller's share is then converted and rounded (`ROUND_HALF_UP`) to that seller's wallet currency before crediting.

## 2. Supported Currencies and Static Conversion Rates
- **Supported Currencies**: **`CAD`** and **`USD`** are supported for both wallet creation (`WalletCreateSerializer`, `WalletCard.jsx`) and cart display currency selection (`backend/commerce/pricing.py`).
- **Storage & Static Rates**: Static conversion rates are stored in a backend configuration dictionary (`CONVERSION_RATES` in `backend/commerce/pricing.py`):
  - `USD -> CAD`: `1.40` (multiply USD by `1.40` to obtain CAD)
  - `CAD -> USD`: `0.714286` (equivalent to `1 / 1.40`, rounded to two decimal places on output)
  - Same-currency pairs (`CAD -> CAD`, `USD -> USD`) use `1.00` without conversion.
- **Application**: Changing the cart's display currency recalculates displayed item prices, tax, delivery, and totals using `CONVERSION_RATES` without modifying original listing prices or the buyer's wallet deduction. If a required currency pair is unsupported, checkout/payment raises a validation error rather than guessing a rate.

## 3. Guest Cart and Wallet Session Lifetime
- **Session Binding**: Unauthenticated guest carts (`Cart` with `user=None`) and temporary guest wallets (`Wallet` with `user=None`) are bound to the browser's Django session key (`session_key`), enforced at the database level via `one_wallet_per_session` and the XOR constraint `wallet_belongs_to_user_or_session`.
- **Guest Notification**: Guests are informed immediately upon wallet creation and on every wallet view/top-up via `WalletSerializer.warning` and a warning banner in `WalletCard.jsx` stating that closing or clearing their browser session permanently loses access to the temporary wallet and balance.
- **Order Access**: Guest orders generate a unique order ID and a cryptographically random `access_token` link (`view_guest_order`); an email address or order number alone cannot access the order.

## 4. Handling Paused/Removed Listings and Suspended/Unverified Accounts
- **Listing State & Stock Changes**: Carts and pending orders do not reserve stock. If a fixed-price listing becomes paused, suspended, expired, or out of stock while in a cart, `cart_warnings()` flags the issue without silently deleting the item. During checkout and again immediately before payment (`recheck_before_payment()`), the server blocks payment and requires the buyer to return to the cart to remove or adjust the affected item.
- **Account Restrictions**: Members must have `items.buy` permission, a verified email (`email_verified=True`), and an `Active` account (`account_state == 'Active'`) to check out or pay, while sellers must hold the `Seller` role, an approved seller application, a verified email, an `Active` account, and a wallet. If a signed-in user is unverified or suspended, the server refuses checkout and payment outright and never treats the signed-in user as an anonymous guest.

## 5. Atomic Payment Execution (Wallet Transfers, Stock Changes, and Order Settlement)
- **Single Atomic Transaction**: Both `pay_order()` (cart orders) and `pay_auction_order()` (Release 5 auction wins) execute inside `@transaction.atomic` (`backend/commerce/payment.py`).
- **Deterministic Row Locking**: Within the transaction, the server acquires row-level database locks (`select_for_update()`) in deterministic primary-key order on the `Order` / `AuctionOrder`, affected `Listing` rows, buyer `Wallet`, and seller `Wallet` rows.
- **All-or-Nothing Execution**: After re-verifying permissions, stock availability, and wallet balance, the transaction debits the buyer wallet, credits each seller wallet in their own currency, records `WalletTransaction` receipts (`Order #<id>` or `AuctionOrder #<id>`), decrements fixed-price stock (transitioning listings at `0` stock to `sold_out`), marks the order `Paid`, and clears/unlocks the buyer's cart. Any validation, balance, or concurrency failure rolls back the entire transaction without changing balances or stock.

## 6. Preventing Duplicate Payments on Already-Paid Orders
- **Locked Status Check & Idempotency**: At the start of `pay_order()` and `pay_auction_order()`, the order row is locked with `select_for_update()` inside the same database transaction as the payment updates. If `payment_status == 'Paid'`, the server immediately returns `{ payment_status: 'Paid', already_paid: True }` without debiting wallets, crediting sellers, or reducing stock a second time.
- **Single Pending Order Constraint**: `start_checkout()` enforces a database constraint (`one_pending_order_per_cart`) so repeated checkout submissions reuse or update the single `Pending` order rather than creating duplicate orders.
