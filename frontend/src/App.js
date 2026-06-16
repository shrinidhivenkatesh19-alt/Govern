import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "@/lib/auth";
import { Toaster } from "@/components/ui/sonner";

import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Shell from "@/components/Shell";
import Overview from "@/pages/Overview";
import NewSubmission from "@/pages/NewSubmission";
import Queue from "@/pages/Queue";
import SubmissionDetail from "@/pages/SubmissionDetail";
import Analytics from "@/pages/Analytics";

function Protected({ children }) {
    const { user, loading } = useAuth();
    if (loading) return <div className="p-10 text-sm text-muted-foreground">Loading...</div>;
    if (!user) return <Navigate to="/login" replace />;
    return children;
}

function PublicOnly({ children }) {
    const { user, loading } = useAuth();
    if (loading) return <div className="p-10 text-sm text-muted-foreground">Loading...</div>;
    if (user) return <Navigate to="/app" replace />;
    return children;
}

export default function App() {
    return (
        <BrowserRouter>
            <AuthProvider>
                <Routes>
                    <Route path="/" element={<Navigate to="/app" replace />} />
                    <Route
                        path="/login"
                        element={
                            <PublicOnly>
                                <Login />
                            </PublicOnly>
                        }
                    />
                    <Route
                        path="/register"
                        element={
                            <PublicOnly>
                                <Register />
                            </PublicOnly>
                        }
                    />
                    <Route
                        path="/app"
                        element={
                            <Protected>
                                <Shell />
                            </Protected>
                        }
                    >
                        <Route index element={<Overview />} />
                        <Route path="submit" element={<NewSubmission />} />
                        <Route path="queue" element={<Queue />} />
                        <Route path="submission/:id" element={<SubmissionDetail />} />
                        <Route path="analytics" element={<Analytics />} />
                    </Route>
                    <Route path="*" element={<Navigate to="/app" replace />} />
                </Routes>
                <Toaster position="top-right" />
            </AuthProvider>
        </BrowserRouter>
    );
}
