"""
CLI principale per il sistema di pianificazione turni PDM.
"""

import sys
import argparse

from ..database.db import Database
from ..importer.pdf_parser import PDFImporter
from ..turn_builder.auto_builder import AutoBuilder
from ..turn_builder.manual_builder import ManualBuilder
from ..validator.rules import TurnValidator


def cmd_import(args, db: Database):
    """Importa un PDF di Turno Materiale."""
    importer = PDFImporter(args.pdf_path, db)
    count = importer.run_import()
    if count == 0:
        print("Importazione fallita o nessun segmento trovato.")
        sys.exit(1)


def cmd_train(args, db: Database):
    """Interrogazione per numero treno."""
    results = db.query_train(args.train_id)
    if not results:
        print(f"Treno {args.train_id} non trovato nel database.")
        return

    print(f"\nTRENO {args.train_id}:")
    print(f"{'Da':<25} {'Partenza':<10} {'A':<25} {'Arrivo':<10} {'Conf':<6}")
    print(f"{'-'*76}")
    for r in results:
        print(
            f"{r['from_station']:<25} {r['dep_time']:<10} "
            f"{r['to_station']:<25} {r['arr_time']:<10} "
            f"{r['confidence']:<6.2f}"
        )
    print()


def cmd_station(args, db: Database):
    """Interrogazione per stazione."""
    station = args.station_name

    departures = db.query_station_departures(station)
    arrivals = db.query_station_arrivals(station)

    print(f"\nSTAZIONE: {station.upper()}")

    if departures:
        print(f"\n  PARTENZE ({len(departures)}):")
        print(f"  {'Treno':<10} {'Ora':<8} {'Destinazione':<30} {'Arrivo':<8}")
        print(f"  {'-'*56}")
        for r in departures:
            print(
                f"  {r['train_id']:<10} {r['dep_time']:<8} "
                f"{r['to_station']:<30} {r['arr_time']:<8}"
            )
    else:
        print(f"\n  Nessuna partenza trovata.")

    if arrivals:
        print(f"\n  ARRIVI ({len(arrivals)}):")
        print(f"  {'Treno':<10} {'Origine':<30} {'Partenza':<8} {'Arrivo':<8}")
        print(f"  {'-'*56}")
        for r in arrivals:
            print(
                f"  {r['train_id']:<10} {r['from_station']:<30} "
                f"{r['dep_time']:<8} {r['arr_time']:<8}"
            )
    else:
        print(f"\n  Nessun arrivo trovato.")
    print()


def cmd_build_auto(args, db: Database):
    """Costruisce turni in modalità automatica."""
    builder = AutoBuilder(db, deposito=args.deposito)
    builder.build_schedule(n_workdays=args.days)


def cmd_build_manual(args, db: Database):
    """Avvia il turn builder manuale interattivo."""
    builder = ManualBuilder(db, deposito=args.deposito)
    builder.run_interactive()


def cmd_info(args, db: Database):
    """Mostra informazioni sul database."""
    count = db.segment_count()
    turns = db.get_material_turns()
    days = db.get_distinct_day_indices()

    print(f"\nDATABASE INFO:")
    print(f"  Segmenti totali: {count}")
    print(f"  Turni materiale: {len(turns)}")
    for t in turns:
        print(f"    Turno {t['turn_number']}: {t['total_segments']} segmenti ({t['source_file']})")
    print(f"  Indici giorno: {days}")

    # Treni unici
    all_segs = db.get_all_segments()
    unique_trains = sorted(set(s["train_id"] for s in all_segs))
    print(f"  Treni unici: {len(unique_trains)}")
    if len(unique_trains) <= 30:
        for tid in unique_trains:
            segs = [s for s in all_segs if s["train_id"] == tid]
            print(f"    {tid}: {len(segs)} segmenti")
    print()


def cmd_clear(args, db: Database):
    """Cancella tutti i dati dal database."""
    confirm = input("Cancellare tutti i dati? (s/n): ").strip().lower()
    if confirm in ("s", "si", "y", "yes"):
        db.clear_all()
        print("Database svuotato.")
    else:
        print("Operazione annullata.")


def run_cli():
    """Entry point CLI."""
    parser = argparse.ArgumentParser(
        prog="app.py",
        description="Sistema Pianificazione Turni PDM - Personale di Macchina",
    )
    parser.add_argument(
        "--db", default="turni.db",
        help="Percorso database SQLite (default: turni.db)",
    )
    subparsers = parser.add_subparsers(dest="command", help="Comandi disponibili")

    # import
    p_import = subparsers.add_parser("import", help="Importa PDF turno materiale")
    p_import.add_argument("pdf_path", help="Percorso del file PDF")

    # train
    p_train = subparsers.add_parser("train", help="Interroga un treno")
    p_train.add_argument("train_id", help="Numero del treno (es. 10020)")

    # station
    p_station = subparsers.add_parser("station", help="Interroga una stazione")
    p_station.add_argument("station_name", help="Nome della stazione")

    # build-auto
    p_auto = subparsers.add_parser("build-auto", help="Builder automatico (greedy)")
    p_auto.add_argument("--deposito", default="", help="Stazione deposito")
    p_auto.add_argument("--days", type=int, default=5, help="Numero giornate (default: 5)")

    # build-manual
    p_manual = subparsers.add_parser("build-manual", help="Builder manuale interattivo")
    p_manual.add_argument("--deposito", default="", help="Stazione deposito")

    # info
    p_info = subparsers.add_parser("info", help="Informazioni database")

    # clear
    p_clear = subparsers.add_parser("clear", help="Cancella database")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    db = Database(db_path=args.db)

    try:
        if args.command == "import":
            cmd_import(args, db)
        elif args.command == "train":
            cmd_train(args, db)
        elif args.command == "station":
            cmd_station(args, db)
        elif args.command == "build-auto":
            cmd_build_auto(args, db)
        elif args.command == "build-manual":
            cmd_build_manual(args, db)
        elif args.command == "info":
            cmd_info(args, db)
        elif args.command == "clear":
            cmd_clear(args, db)
        else:
            parser.print_help()
    finally:
        db.close()
