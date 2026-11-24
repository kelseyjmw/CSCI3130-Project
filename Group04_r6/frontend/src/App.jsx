import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import NavBar from './components/NavBar';
import Register from './components/Register';
import VerifyEmail from './components/VerifyEmail';
import Login from './pages/Login';
import PasswordReset from './pages/PasswordReset';
import Dashboard from './pages/Dashboard';
import Applications from './pages/Applications';
import RequireAuth from './components/RequireAuth';
import { AuthProvider } from './context/AuthContext';
import ResendVerification from './components/ResendVerification';
import ReviewQueue from './pages/ReviewQueue';
import Profile from "./pages/Profile"
import PublicProfile from './pages/PublicProfile';
import Account from "./pages/Account"
import AdminPanel from './pages/AdminPanel';
import Catalog from './pages/Catalog';
import Cart from './pages/Cart';
import Checkout from './pages/Checkout';
import Order from './pages/Order';
import GuestOrder from './pages/GuestOrder';
import AuctionOrderPay from './pages/AuctionOrderPay';
import MyListings from './pages/MyListings';
import ListingDetail from './pages/ListingDetail';
import ListingForm from './pages/ListingForm';
import './index.css';
import './components/AppForm.css'
import VerifyEmailChange from './components/VerifyEmailChange';
import AuctionNotifications from './components/AuctionNotifications';

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <NavBar />
        <div className="App">
          <Routes>
            <Route path="/" element={<Navigate to="/catalog" replace />} />
            <Route path="/catalog" element={<Catalog />} />
            <Route path="/cart" element={<Cart />} />
            <Route path="/checkout" element={<Checkout />} />
            <Route path="/orders/guest/:token" element={<GuestOrder />} />
            <Route path="/orders/:orderId" element={<Order />} />
            <Route path="/auction-orders/:auctionOrderId" element={<RequireAuth><AuctionOrderPay /></RequireAuth>} />
            <Route path="/my-listings" element={<RequireAuth><MyListings /></RequireAuth>} />
            <Route path="/notifications" element={<RequireAuth><main className="page"><AuctionNotifications /></main></RequireAuth>} />
            <Route path="/listings/new" element={<RequireAuth><ListingForm /></RequireAuth>} />
            <Route path="/listings/:id/edit" element={<RequireAuth><ListingForm /></RequireAuth>} />
            <Route path="/listings/:id" element={<ListingDetail />} />
            <Route path="/register" element={<Register />} />
            <Route path="/verify-email/:token" element={<VerifyEmail />} />
            <Route path="/verify-email-change/:token" element={<VerifyEmailChange />} />
            <Route path="/resend-verification" element={<ResendVerification />} />
            <Route path="/login" element={<Login />} />
            <Route path="/forgot-password" element={<PasswordReset key="request" />} />
            <Route path="/reset-password/:token" element={<PasswordReset key="confirm" />} />
            <Route path="/profiles/:userId" element={<PublicProfile />} />
            <Route
              path="/dashboard"
              element={
                <RequireAuth>
                  <Dashboard />
                </RequireAuth>
              }
            />
            <Route
              path="/applications"
              element={
                <RequireAuth>
                  <Applications />
                </RequireAuth>
              }
            />
            <Route 
              path="/review-queue" 
              element={
                <RequireAuth>
                  <ReviewQueue />
                </RequireAuth>
              }
            />
            <Route 
              path="/profile" 
              element={
                <RequireAuth>
                  <Profile />
                </RequireAuth>
              }
            />
            <Route 
              path="/account" 
              element={
                <RequireAuth>
                  <Account />
                </RequireAuth>
              }
            />
            <Route 
              path="/admin-panel" 
              element={
                <RequireAuth>
                  <AdminPanel />
                </RequireAuth>
              }
            />
            <Route path="*" element={<Navigate to="/register" replace />} />
          </Routes>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;

