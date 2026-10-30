import { Navigate, Route, Routes } from "react-router";

import AppLayout from "./components/layout/AppLayout";

import PatientDashboard from "./pages/patient/PatientDashboard";
import DoctorDashboard from "./pages/doctor/DoctorDashboard";
import PatientDetails from "./pages/doctor/PatientDetails";
import ProfilePage from "./pages/profile/ProfilePage";
import AlertsPage from "./pages/alerts/AlertsPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        {/* Default route */}
        <Route path="/" element={<Navigate to="/patient" replace />} />

        {/* Patient */}
        <Route path="/patient" element={<PatientDashboard />} />

        {/* Doctor */}
        <Route path="/doctor" element={<DoctorDashboard />} />
        <Route
          path="/doctor/patients/:patientId"
          element={<PatientDetails />}
        />

        {/* General pages */}
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/alerts" element={<AlertsPage />} />

        {/* 404 */}
        <Route
          path="*"
          element={
            <section className="rounded-2xl border border-slate-200 bg-white p-8">
              <h1 className="text-2xl font-bold text-slate-900">
                Page introuvable
              </h1>

              <p className="mt-2 text-slate-500">
                La page demandée n'existe pas.
              </p>
            </section>
          }
        />
      </Route>
    </Routes>
  );
}