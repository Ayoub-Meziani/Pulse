import { Navigate, Route, Routes } from "react-router";
import AlertsPage from "./pages/alerts/AlertsPage";
import AppLayout from "./components/layout/AppLayout";
import PatientDetails from "./pages/doctor/PatientDetails";
import PatientDashboard from "./pages/patient/PatientDashboard";
import DoctorDashboard from "./pages/doctor/DoctorDashboard";
import ProfilePage from "./pages/profile/ProfilePage";

export default function App() {
  return (
    <Routes>

      <Route element={<AppLayout />}>
        <Route
          path="/"
          element={<Navigate to="/patient" replace />}
        />

        <Route
          path="/patient"
          element={<PatientDashboard />}
        />

        <Route
          path="/doctor"
          element={<DoctorDashboard />}
        />
        <Route
          path="/doctor/patients/:patientId"
          element={<PatientDetails />}
        />

        <Route
          path="/profile"
          element={<ProfilePage />}
        />
        <Route 
        path="/alerts" element={<AlertsPage />}
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

    </Routes>
  );
}