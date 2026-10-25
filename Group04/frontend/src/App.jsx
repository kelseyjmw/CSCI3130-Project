import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import NavBar from './components/NavBar';
import Register from './components/Register';
import VerifyEmail from './components/VerifyEmail';
import Login from './pages/Login';
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
import MyListings from './pages/MyListings';
import ListingDetail from './pages/ListingDetail';
import ListingForm from './pages/ListingForm';
import './index.css';
import './components/AppForm.css'
import VerifyEmailChange from './components/VerifyEmailChange';

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <NavBar />
        <div className="App">
          <Routes>
            <Route path="/" element={<Navigate to="/catalog" replace />} />
            <Route path="/catalog" element={<Catalog />} />
            <Route path="/my-listings" element={<RequireAuth><MyListings /></RequireAuth>} />
            <Route path="/listings/new" element={<RequireAuth><ListingForm /></RequireAuth>} />
            <Route path="/listings/:id/edit" element={<RequireAuth><ListingForm /></RequireAuth>} />
            <Route path="/listings/:id" element={<ListingDetail />} />
            <Route path="/register" element={<Register />} />
            <Route path="/verify-email/:token" element={<VerifyEmail />} />
            <Route path="/verify-email-change/:token" element={<VerifyEmailChange />} />
            <Route path="/resend-verification" element={<ResendVerification />} />
            <Route path="/login" element={<Login />} />
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
