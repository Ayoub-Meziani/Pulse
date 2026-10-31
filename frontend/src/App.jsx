import { Navigate, Route, Routes } from "react-router";
import NotificationsPage from "./pages/NotificationsPage";
import AppLayout from "./components/layout/AppLayout";
import RequireRole from "./auth/RequireRole";
import { homeFor } from "./auth/roles";
import { useAuth } from "./auth/AuthContext";
import AdminPage from "./pages/admin/AdminPage";
import AlertsPage from "./pages/alerts/AlertsPage";
import LoginPage from "./pages/auth/LoginPage";
import DoctorDashboard from "./pages/doctor/DoctorDashboard";
import PatientDetails from "./pages/doctor/PatientDetails";
import AddReading from "./pages/patient/AddReading";
import EmergencyScreen from "./pages/patient/EmergencyScreen";
import HistoryPage from "./pages/patient/HistoryPage";
import JournalPage from "./pages/patient/JournalPage";
import PatientDashboard from "./pages/patient/PatientDashboard";
import ProfilePage from "./pages/profile/ProfilePage";
import { ButtonLink } from "./components/ui/Button";

function HomeRedirect() {
  const { user } = useAuth();
  return <Navigate to={homeFor(user.role) ?? "/login"} replace />;
}

function NotFound() {
  return (
    <section className="mx-auto mt-10 max-w-md rounded-2xl border border-line bg-surface p-8 text-center">
      <h1 className="text-xl font-bold text-ink">Page introuvable</h1>
      <p className="mt-2 text-ink-muted">La page demandée n'existe pas.</p>
      <ButtonLink to="/" className="mt-5">Retour à l'accueil</ButtonLink>
    </section>
  );
}

// Roles come from the server (/me). Every screen reads real data through the API, which authorizes each
// request itself: these guards only choose what to show.
export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<RequireRole roles={["patient", "doctor", "admin"]} />}>
        <Route element={<AppLayout />}>
          <Route path="/" element={<HomeRedirect />} />
          <Route element={<RequireRole roles={["patient", "doctor"]} />}>
            <Route path="/notifications" element={<NotificationsPage />} />
          </Route>

          <Route element={<RequireRole roles={["patient"]} />}>
            <Route path="/patient" element={<PatientDashboard />} />
            <Route path="/patient/mesure" element={<AddReading />} />
            <Route path="/patient/urgence" element={<EmergencyScreen />} />
            <Route path="/patient/historique" element={<HistoryPage />} />
            <Route path="/patient/alertes" element={<AlertsPage />} />
            <Route path="/patient/journal" element={<JournalPage />} />
            <Route path="/patient/profil" element={<ProfilePage />} />
          </Route>

          <Route element={<RequireRole roles={["doctor"]} />}>
            <Route path="/doctor" element={<DoctorDashboard />} />
            <Route path="/doctor/patients/:patientId" element={<PatientDetails />} />
          </Route>

          <Route element={<RequireRole roles={["admin"]} />}>
            <Route path="/admin" element={<AdminPage />} />
          </Route>

          <Route path="/profile" element={<Navigate to="/patient/profil" replace />} />
          <Route path="/alerts" element={<Navigate to="/patient/alertes" replace />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
    </Routes>
  );
}
