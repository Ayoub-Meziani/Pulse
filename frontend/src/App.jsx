import { Navigate, Route, Routes } from "react-router";

import AppLayout from "./components/layout/AppLayout";

import LoginPage from "./pages/auth/LoginPage";
import PatientDashboard from "./pages/patient/PatientDashboard";
import DoctorDashboard from "./pages/doctor/DoctorDashboard";
import PatientDetails from "./pages/doctor/PatientDetails";
import AlertsPage from "./pages/alerts/AlertsPage";
import ProfilePage from "./pages/profile/ProfilePage";

export default function App() {
  return (
    <Routes>
      {/* Page de connexion : sans sidebar ni header */}
      <Route path="/login" element={<LoginPage />} />

      {/* Redirection vers la connexion */}
      <Route path="/" element={<Navigate to="/login" replace />} />

      {/* Pages de l'application */}
      <Route element={<AppLayout />}>
        <Route path="/patient" element={<PatientDashboard />} />

        <Route path="/doctor" element={<DoctorDashboard />} />

        <Route
          path="/doctor/patients/:patientId"
          element={<PatientDetails />}
        />

        <Route path="/profile" element={<ProfilePage />} />

        <Route path="/alerts" element={<AlertsPage />} />
      </Route>

      {/* Page introuvable */}
      <Route
        path="*"
        element={<Navigate to="/login" replace />}
      />
    </Routes>
  );
}