#!/usr/bin/env python3
"""Emails (or, as a fallback, saves to disk) the monthly model-watch report.

Runs on the HOST, not in a container — plain stdlib (smtplib) so it works
without any Python deps beyond a normal python3 install. SMTP settings come
from the environment (see .env.example's "Surveillance mensuelle des
modèles" section) since check_model.sh sources .env before calling this.
"""

import argparse
import json
import os
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

REPORTS_DIR = Path(__file__).parent / "reports"


def build_body(old_model: str, new_model: str, result: dict | None, error: str | None) -> str:
    lines = [f"Vérification mensuelle des modèles Ollama — {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}", ""]

    if error:
        lines += [f"ÉCHEC : {error}", "", f"Modèle en place (inchangé) : {old_model}"]
        return "\n".join(lines)

    if old_model != new_model:
        lines += [
            f"CHANGEMENT APPLIQUÉ : {old_model}  →  {new_model}",
            "",
            "Pour revenir en arrière :",
            f"  1. Dans .env, remettre OLLAMA_MODEL={old_model}",
            "  2. docker compose up -d --no-deps backend",
            "",
        ]
    else:
        lines += [f"Aucun changement — modèle actuel conservé : {old_model}", ""]

    lines.append(f"VRAM GPU : {result['vram_total_gb']} Go (budget modèle utilisé : {result['vram_budget_gb']} Go)")
    lines.append("")

    b = result["baseline"]
    lines.append(f"Modèle actuel  {b['model']:<30} score {b['avg_score']:>5.1f}/100   latence moy. {b['avg_latency_s']}s")
    for c in result["candidates"]:
        marker = " <-- retenu" if c["model"] == new_model and old_model != new_model else ""
        lines.append(
            f"Candidat       {c['model']:<30} score {c['avg_score']:>5.1f}/100   "
            f"latence moy. {c['avg_latency_s']}s   ~{c['disk_size_gb']} Go{marker}"
        )

    if result.get("warnings"):
        lines += ["", "Avertissements :"]
        lines += [f"  - {w}" for w in result["warnings"]]

    detail_model = result["baseline"] if new_model == b["model"] else next(
        (c for c in result["candidates"] if c["model"] == new_model), b
    )
    lines += ["", f"Détail par cas de test ({detail_model['model']}) :"]
    for case in detail_model["cases"]:
        lines.append(f"  [{case['case']}] {case['score']}/100 ({case['latency_s']}s)")
        for note in case["notes"]:
            lines.append(f"      {note}")

    return "\n".join(lines)


def send_email(subject: str, body: str) -> bool:
    host = os.environ.get("MODEL_WATCH_SMTP_HOST")
    to_addr = os.environ.get("MODEL_WATCH_SMTP_TO")
    if not host or not to_addr:
        print("model_watch: MODEL_WATCH_SMTP_HOST/MODEL_WATCH_SMTP_TO absents — email non envoyé.", file=sys.stderr)
        return False

    port = int(os.environ.get("MODEL_WATCH_SMTP_PORT", "587"))
    user = os.environ.get("MODEL_WATCH_SMTP_USER")
    password = os.environ.get("MODEL_WATCH_SMTP_PASSWORD")
    from_addr = os.environ.get("MODEL_WATCH_SMTP_FROM", user or to_addr)
    use_tls = os.environ.get("MODEL_WATCH_SMTP_USE_TLS", "true").lower() != "false"

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr

    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            if use_tls:
                server.starttls()
            if user and password:
                server.login(user, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        return True
    except Exception as e:
        print(f"model_watch: échec de l'envoi de l'email : {e}", file=sys.stderr)
        return False


def save_local_copy(subject: str, body: str) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"{datetime.now(timezone.utc):%Y-%m-%d}.txt"
    path.write_text(f"{subject}\n\n{body}\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-model", required=True)
    parser.add_argument("--new-model", required=True)
    parser.add_argument("--error", default=None)
    args = parser.parse_args()

    result = None
    if args.error is None:
        raw = sys.stdin.read()
        result = json.loads(raw) if raw.strip() else None

    body = build_body(args.old_model, args.new_model, result, args.error)

    if args.error:
        subject = "[Popote] Échec de la vérification mensuelle des modèles"
    elif args.old_model != args.new_model:
        subject = f"[Popote] Modèle changé : {args.old_model} → {args.new_model}"
    else:
        subject = "[Popote] Vérification mensuelle des modèles — rien de nouveau"

    sent = send_email(subject, body)
    local_path = save_local_copy(subject, body)
    print(f"model_watch: rapport {'envoyé par email et ' if sent else 'NON envoyé par email (voir ci-dessus), '}"
          f"enregistré dans {local_path}")


if __name__ == "__main__":
    main()
