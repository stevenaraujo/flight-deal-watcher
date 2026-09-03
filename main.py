#!/usr/bin/env python3
"""
Flight Deal Watcher ZRH -> GIG
Haupt-Einstiegspunkt / CLI.

Nutzung:
    python main.py                 # normaler Lauf (sucht, speichert, benachrichtigt)
    python main.py --dry-run       # sucht und zeigt Ergebnis, verschickt NICHTS
    python main.py --test-telegram # sendet eine Test-Nachricht via Telegram
    python main.py --test-email    # sendet eine Test-E-Mail
"""
from __future__ import annotations

import argparse
import logging
import sys

from src import config, filters, storage
from src.dashboard import write_dashboard
from src.deal_engine import assess, rank_offers, should_notify
from src.logging_setup import setup_logging
from src.notifiers import email_notifier, telegram
from src.notifiers.message_formatter import format_deal_message
from src.providers import serpapi_provider
from src.providers.serpapi_provider import ProviderError

logger = logging.getLogger("flight_watcher.main")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Flight Deal Watcher ZRH -> GIG")
    parser.add_argument("--dry-run", action="store_true", help="Suche ausführen, aber nichts versenden.")
    parser.add_argument("--test-telegram", action="store_true", help="Nur eine Telegram-Testnachricht senden.")
    parser.add_argument("--test-email", action="store_true", help="Nur eine Test-E-Mail senden.")
    return parser.parse_args()


def run_test_telegram() -> int:
    ok = telegram.send_message("✅ Flight Deal Watcher: Telegram-Testnachricht erfolgreich.")
    print("Telegram-Test:", "OK" if ok else "FEHLGESCHLAGEN")
    return 0 if ok else 1


def run_test_email() -> int:
    ok = email_notifier.send_email(
        "Flight Deal Watcher – Test", "Dies ist eine Test-E-Mail des Flight Deal Watchers ZRH -> GIG."
    )
    print("E-Mail-Test:", "OK" if ok else "FEHLGESCHLAGEN")
    return 0 if ok else 1


def run_watch(dry_run: bool) -> int:
    if not config.BUDGET_OK:
        logger.warning(
            "Konfiguriertes API-Budget (%s Requests/Monat) überschreitet das SerpApi-Free-Tier (%s)!",
            config.MONTHLY_REQUEST_COST, config.SERPAPI_FREE_TIER_SEARCHES_PER_MONTH,
        )

    storage.init_db()
    run_id = storage.start_run()

    combo_indices = storage.get_next_combo_indices(config.DAILY_COMBINATIONS_TO_CHECK)
    combos = [config.ALL_COMBINATIONS[i] for i in combo_indices]
    logger.info("Prüfe %s Datumskombinationen: %s", len(combos), combos)

    all_offers = []
    api_calls_used = 0
    had_error = False
    error_message = None

    for outbound_date, return_date in combos:
        try:
            offers = serpapi_provider.search_round_trip(outbound_date, return_date)
            api_calls_used += config.REQUESTS_PER_COMBINATION
            all_offers.extend(offers)
        except ProviderError as exc:
            logger.error("Provider-Fehler bei %s -> %s: %s", outbound_date, return_date, exc)
            had_error = True
            error_message = str(exc)
            continue

    valid_offers = filters.filter_offers(all_offers)
    logger.info("%s von %s Angeboten erfüllen alle Mindestanforderungen.", len(valid_offers), len(all_offers))

    historical_low = storage.get_historical_low()
    already_notified = storage.get_notified_keys()

    assessments = []
    for offer in valid_offers:
        previous_price = storage.get_previous_price_for_combo(offer.outbound_date, offer.return_date)
        assessment = assess(offer, historical_low, previous_price)
        storage.save_observation(offer, assessment)
        assessments.append(assessment)
        # Nach dem Speichern kann sich der historische Tiefstpreis für die
        # nächste Iteration innerhalb desselben Laufs geändert haben:
        if assessment.is_all_time_low:
            historical_low = assessment.offer.total_effective_price_per_person

    ranked = rank_offers(assessments)

    to_notify = [a for a in ranked if should_notify(a, already_notified)]
    logger.info("%s neue Benachrichtigung(en) fällig.", len(to_notify))

    if not dry_run:
        for assessment in to_notify:
            message = format_deal_message(assessment, storage.get_historical_low())
            telegram_ok = telegram.send_message(message)
            email_ok = email_notifier.send_email(
                subject=f"Flug-Deal ZRH->Rio: {assessment.tier_label} – CHF {assessment.offer.total_effective_price_per_person:,.0f}",
                body=message,
            )
            if telegram_ok or email_ok:
                storage.mark_notified(assessment.offer.unique_key())
            else:
                logger.warning("Weder Telegram noch E-Mail erfolgreich für %s", assessment.offer.unique_key())
    else:
        print("\n--- DRY RUN: gefundene Angebote (keine Benachrichtigung verschickt) ---\n")
        for assessment in ranked[:10]:
            print(format_deal_message(assessment, historical_low))
            print("-" * 60)

    storage.advance_rotation(len(combos))
    write_dashboard()

    consecutive_failures = storage.get_consecutive_failed_runs()
    status = "failed" if had_error and not valid_offers else "ok"
    storage.finish_run(run_id, status, len(combos), len(valid_offers), api_calls_used, error_message)

    if status == "failed" and consecutive_failures + 1 >= 3:
        alert = (
            f"⚠️ Flight Deal Watcher: {consecutive_failures + 1} Läufe in Folge fehlgeschlagen.\n"
            f"Letzter Fehler: {error_message}"
        )
        telegram.send_message(alert)
        email_notifier.send_email("Flight Deal Watcher – wiederholter Fehler", alert)

    return 0


def main() -> int:
    setup_logging()
    args = parse_args()

    if args.test_telegram:
        return run_test_telegram()
    if args.test_email:
        return run_test_email()
    return run_watch(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
