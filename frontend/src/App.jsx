import { Navigate, Route, Routes } from "react-router";
import AlertsPage from "./pages/alerts/AlertsPage";
import AppLayout from "./components/layout/AppLayout";
import PatientDetails from "./pages/doctor/PatientDetails";
import PatientDashboard from "./pages/patient/PatientDashboard";
import DoctorDashboard from "./pages/doctor/DoctorDashboard";
import ProfilePage from "./pages/profile/ProfilePage";
import RequireRole from "./auth/RequireRole";
import { homeFor } from "./auth/roles";
import { useAuth } from "./auth/AuthContext";
import LoginPage from "./pages/auth/LoginPage";

function HomeRedirect() {
  const { user } = useAuth();
  return <Navigate to={homeFor(user.role) ?? "/login"} replace />;
}

// Roles come from the server (/me). Doctor, alerts and profile pages still show demo data until
// they are connected to the API; they are only reachable after login.
export default function App() {
  return (
    <Routes>

      <Route path="/login" element={<LoginPage />} />

      <Route element={<RequireRole roles={["patient", "doctor"]} />}>
        <Route element={<AppLayout />}>
          <Route path="/" element={<HomeRedirect />} />

          <Route element={<RequireRole roles={["patient"]} />}>
            <Route
              path="/patient"
              element={<PatientDashboard />}
            />
          </Route>

          <Route element={<RequireRole roles={["doctor"]} />}>
            <Route
              path="/doctor"
              element={<DoctorDashboard />}
            />
            <Route
              path="/doctor/patients/:patientId"
              element={<PatientDetails />}
            />
          </Route>

          <Route
            path="/profile"
            element={<ProfilePage />}
          />
          <Route
            path="/alerts"
            element={<AlertsPage />}
          />

          <Route
            path="*"
            element={
              <section className="rounded-2xl bg-white p-8 shadow-sm">
                <h1 className="text-2xl font-bold">
                  Page introuvable
                </h1>

                <p className="mt-2 text-slate-600">
                  La page demandée n'existe pas.
                </p>
              </section>
            }
          />
        </Route>
      </Route>

    </Routes>
  );
}
