import { BrowserRouter, Routes, Route } from "react-router-dom"
import { Layout } from "@/components/Layout"
import { LoginPage } from "@/pages/LoginPage"
import { DashboardPage } from "@/pages/DashboardPage"
import { TrainSearchPage } from "@/pages/TrainSearchPage"
import { ShiftsPage } from "@/pages/ShiftsPage"
import { PlaceholderPage } from "@/pages/PlaceholderPage"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="treni" element={<TrainSearchPage />} />
          <Route path="turni" element={<ShiftsPage />} />
          <Route path="calendario" element={<PlaceholderPage title="Calendario" />} />
          <Route path="import" element={<PlaceholderPage title="Import PDF" />} />
          <Route path="impostazioni" element={<PlaceholderPage title="Impostazioni" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
