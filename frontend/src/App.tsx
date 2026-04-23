import { BrowserRouter, Routes, Route } from "react-router-dom"
import { Layout } from "@/components/Layout"
import { LoginPage } from "@/pages/LoginPage"
import { DashboardPage } from "@/pages/DashboardPage"
import { ShiftsPage } from "@/pages/ShiftsPage"
import { BuilderPage } from "@/pages/BuilderPage"
import { CalendarAgentePage } from "@/pages/CalendarAgentePage"
import { ImportPage } from "@/pages/ImportPage"
import { PdcPage } from "@/pages/PdcPage"
import { PdcBuilderPage } from "@/pages/PdcBuilderPage"
import { PdcDepotPage } from "@/pages/PdcDepotPage"
import { AutoBuilderPage } from "@/pages/AutoBuilderPage"
import { FRApprovalsPage } from "@/pages/FRApprovalsPage"
import { SettingsPage } from "@/pages/SettingsPage"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="turni" element={<ShiftsPage />} />
          <Route path="builder" element={<BuilderPage />} />
          <Route path="calendario-agente" element={<CalendarAgentePage />} />
          <Route path="pdc" element={<PdcPage />} />
          <Route path="pdc/new" element={<PdcBuilderPage />} />
          <Route path="pdc/edit" element={<PdcBuilderPage />} />
          <Route path="pdc/depot/:impianto" element={<PdcDepotPage />} />
          <Route path="auto-genera" element={<AutoBuilderPage />} />
          <Route path="fr-approvati" element={<FRApprovalsPage />} />
          <Route path="import" element={<ImportPage />} />
          <Route path="impostazioni" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
