import { createContext, useContext, useState, useEffect, useCallback } from "react";
import { getMe, logout as logoutApi } from "../api/auth";

const AuthContext = createContext(undefined);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(undefined);
    const [loading, setLoading] = useState(true);

    const refresh = useCallback(async () => {
        try {
            const data = await getMe();
            setUser(data);
            return data;
        } catch (error) {
            setUser(null);
            return null;
        } finally {
            setLoading(false);
        }
    }, []);

    async function logout() {
        try {
            await logoutApi();
        } finally {
            setUser(null);
        }
    }

    useEffect(() => {
        refresh();
    }, []);

    return (
        <AuthContext.Provider value={{ user, loading, refresh, logout }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error("useAuth must be used within an AuthProvider");
    }
    return context;
}