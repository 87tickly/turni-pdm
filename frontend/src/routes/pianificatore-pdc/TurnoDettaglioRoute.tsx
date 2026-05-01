/**
 * Sprint 7.3 MR 3 — Editor turno PdC sotto path PIANIFICATORE_PDC.
 *
 * Il viewer Gantt è il componente unico
 * `TurnoPdcDettaglioRoute` definito in `pianificatore-giro/`. Lo
 * riusiamo qui sotto path PdC: il componente è path-aware (usa
 * `useLocation` per il back-link) e mostra la stessa UI in entrambi
 * i contesti.
 *
 * Per ora il "editor" è in realtà un visualizzatore Gantt (sola
 * lettura). Le funzionalità di edit (drag&drop blocchi, modifica
 * orari) sono scope MR 4+ / Sprint 8.
 */
export { TurnoPdcDettaglioRoute as PianificatorePdcTurnoDettaglioRoute } from "@/routes/pianificatore-giro/TurnoPdcDettaglioRoute";
