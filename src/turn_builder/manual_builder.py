"""
Turn Builder Manuale - sessione CLI interattiva.
"""

from ..database.db import Database
from ..validator.rules import TurnValidator, DaySummary, _fmt_min, _time_to_min
from ..constants import (
    MAX_PRESTAZIONE_MIN,
    MAX_CONDOTTA_MIN,
    MEAL_MIN,
    WORK_BLOCK,
    REST_BLOCK,
)


class ManualBuilder:
    """Builder manuale interattivo per turni PDM."""

    def __init__(self, db: Database, deposito: str = ""):
        self.db = db
        self.deposito = deposito.upper()
        self.validator = TurnValidator(deposito=self.deposito)
        self.current_segments: list[dict] = []
        self.days: list[DaySummary] = []

    def _show_status(self):
        """Mostra stato corrente della giornata in costruzione."""
        if not self.current_segments:
            print("\n  [Giornata vuota - nessun treno aggiunto]\n")
            return

        summary = self.validator.validate_day(
            self.current_segments, deposito=self.deposito
        )
        print(f"\n  --- STATO GIORNATA CORRENTE ---")
        print(summary.format_output())
        print(f"  Treni nella giornata: {len(self.current_segments)}")
        for i, seg in enumerate(self.current_segments, 1):
            tid = seg.get("train_id", "?")
            fs = seg.get("from_station", "?")
            dt = seg.get("dep_time", "?")
            ts = seg.get("to_station", "?")
            at = seg.get("arr_time", "?")
            print(f"    {i}. Treno {tid}: {fs} {dt} -> {ts} {at}")
        print()

    def _show_departures(self, station: str):
        """Mostra partenze da una stazione."""
        results = self.db.query_station_departures(station)
        if not results:
            print(f"\n  Nessuna partenza trovata da '{station}'.\n")
            return

        print(f"\n  PARTENZE DA {station.upper()}:")
        print(f"  {'Treno':<10} {'Ora':<8} {'Destinazione':<30} {'Arrivo':<8}")
        print(f"  {'-'*56}")
        for r in results:
            print(
                f"  {r['train_id']:<10} {r['dep_time']:<8} "
                f"{r['to_station']:<30} {r['arr_time']:<8}"
            )
        print()

    def _show_arrivals(self, station: str):
        """Mostra arrivi a una stazione."""
        results = self.db.query_station_arrivals(station)
        if not results:
            print(f"\n  Nessun arrivo trovato a '{station}'.\n")
            return

        print(f"\n  ARRIVI A {station.upper()}:")
        print(f"  {'Treno':<10} {'Origine':<30} {'Partenza':<8} {'Arrivo':<8}")
        print(f"  {'-'*56}")
        for r in results:
            print(
                f"  {r['train_id']:<10} {r['from_station']:<30} "
                f"{r['dep_time']:<8} {r['arr_time']:<8}"
            )
        print()

    def _add_train(self, train_id: str):
        """Aggiunge un treno alla giornata corrente."""
        segments = self.db.query_train(train_id)
        if not segments:
            print(f"\n  Treno {train_id} non trovato nel database.\n")
            return

        if len(segments) == 1:
            seg = segments[0]
        else:
            print(f"\n  Treno {train_id} ha {len(segments)} segmenti:")
            for i, s in enumerate(segments, 1):
                print(
                    f"    {i}. {s['from_station']} {s['dep_time']} -> "
                    f"{s['to_station']} {s['arr_time']}"
                )
            try:
                choice = input("  Seleziona segmento (numero) o 'all' per tutti: ").strip()
            except (EOFError, KeyboardInterrupt):
                return

            if choice.lower() == "all":
                for s in segments:
                    self.current_segments.append(s)
                    print(
                        f"  + Aggiunto: {s['train_id']} "
                        f"{s['from_station']} {s['dep_time']} -> "
                        f"{s['to_station']} {s['arr_time']}"
                    )
                self._show_status()
                return

            try:
                idx = int(choice) - 1
                if 0 <= idx < len(segments):
                    seg = segments[idx]
                else:
                    print("  Selezione non valida.")
                    return
            except ValueError:
                print("  Input non valido.")
                return

        self.current_segments.append(seg)
        print(
            f"  + Aggiunto: {seg['train_id']} "
            f"{seg['from_station']} {seg['dep_time']} -> "
            f"{seg['to_station']} {seg['arr_time']}"
        )
        self._show_status()

    def _remove_last(self):
        """Rimuove l'ultimo treno aggiunto."""
        if not self.current_segments:
            print("\n  Nessun treno da rimuovere.\n")
            return

        removed = self.current_segments.pop()
        print(
            f"  - Rimosso: {removed.get('train_id', '?')} "
            f"{removed.get('from_station', '?')} -> {removed.get('to_station', '?')}"
        )
        self._show_status()

    def _validate_day(self) -> DaySummary:
        """Valida la giornata corrente."""
        summary = self.validator.validate_day(
            self.current_segments, deposito=self.deposito
        )
        print(f"\n  === VALIDAZIONE GIORNATA ===")
        print(summary.format_output())
        if not summary.violations:
            print(f"  RISULTATO: VALIDA")
        else:
            print(f"  RISULTATO: {len(summary.violations)} violazione/i")
        print()
        return summary

    def _finalize_day(self):
        """Finalizza la giornata corrente e inizia una nuova."""
        if not self.current_segments:
            print("\n  Nessun treno nella giornata. Niente da finalizzare.\n")
            return

        summary = self._validate_day()
        self.days.append(summary)

        day_num = len(self.days)
        print(f"  Giornata #{day_num} finalizzata con {len(self.current_segments)} treni.")

        if summary.violations:
            print(f"  ATTENZIONE: {len(summary.violations)} violazione/i presenti.")
            for v in summary.violations:
                print(f"    [{v.severity}] {v.rule}: {v.message}")

        self.current_segments = []
        print(f"\n  Nuova giornata iniziata. Usa 'add-train' per aggiungere treni.\n")

    def _show_help(self):
        print("""
  COMANDI DISPONIBILI:
    station departures <STAZIONE>  - Mostra partenze da stazione
    station arrivals <STAZIONE>    - Mostra arrivi a stazione
    add-train <TRAIN_ID>           - Aggiunge treno alla giornata
    remove-last                    - Rimuove ultimo treno
    validate-day                   - Valida giornata corrente
    finalize-day                   - Finalizza giornata e inizia nuova
    show                           - Mostra stato corrente
    days                           - Mostra riepilogo giornate completate
    calendar <N>                   - Genera calendario 5+2 per N giornate
    help                           - Mostra questo help
    quit / exit                    - Esci dalla sessione
        """)

    def _show_completed_days(self):
        """Mostra riepilogo giornate completate."""
        if not self.days:
            print("\n  Nessuna giornata completata.\n")
            return

        print(f"\n  === GIORNATE COMPLETATE: {len(self.days)} ===")
        for i, day in enumerate(self.days, 1):
            print(f"\n  Giornata #{i}:")
            print(day.format_output())
        print()

    def _generate_calendar(self, n_str: str):
        """Genera calendario 5+2."""
        try:
            n = int(n_str)
        except ValueError:
            print("  Numero non valido.")
            return

        calendar = self.validator.build_calendar(n)

        print(f"\n  === CALENDARIO 5+2 per {n} giornate ===")
        row = []
        for entry in calendar:
            row.append(entry["type"][:4])
            if len(row) == 7:
                print(f"  {' '.join(row)}")
                row = []
        if row:
            print(f"  {' '.join(row)}")

        # Valida riposo settimanale
        weekly_v = self.validator.validate_weekly_rest(calendar)
        if weekly_v:
            for v in weekly_v:
                print(f"  [{v.severity}] {v.rule}: {v.message}")
        print()

    def run_interactive(self):
        """Avvia la sessione interattiva."""
        print(f"\n{'='*60}")
        print(f"TURN BUILDER - MODALITA' MANUALE")
        print(f"Deposito: {self.deposito or 'non specificato'}")
        print(f"{'='*60}")
        print(f"  Digita 'help' per la lista comandi.\n")

        while True:
            try:
                raw_input = input("PDM> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  Sessione terminata.")
                break

            if not raw_input:
                continue

            parts = raw_input.split(maxsplit=2)
            cmd = parts[0].lower()

            if cmd in ("quit", "exit"):
                if self.current_segments:
                    print("  Attenzione: giornata corrente non finalizzata.")
                    try:
                        confirm = input("  Uscire comunque? (s/n): ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        break
                    if confirm not in ("s", "si", "y", "yes"):
                        continue
                print("  Sessione terminata.")
                break

            elif cmd == "help":
                self._show_help()

            elif cmd == "show":
                self._show_status()

            elif cmd == "days":
                self._show_completed_days()

            elif cmd == "station" and len(parts) >= 3:
                subcmd = parts[1].lower()
                station = parts[2].strip().strip('"').strip("'")
                if subcmd == "departures":
                    self._show_departures(station)
                elif subcmd == "arrivals":
                    self._show_arrivals(station)
                else:
                    print(f"  Comando sconosciuto: station {subcmd}")

            elif cmd == "add-train" and len(parts) >= 2:
                self._add_train(parts[1])

            elif cmd == "remove-last":
                self._remove_last()

            elif cmd == "validate-day":
                self._validate_day()

            elif cmd == "finalize-day":
                self._finalize_day()

            elif cmd == "calendar" and len(parts) >= 2:
                self._generate_calendar(parts[1])

            else:
                print(f"  Comando non riconosciuto: {raw_input}")
                print(f"  Digita 'help' per la lista comandi.")
