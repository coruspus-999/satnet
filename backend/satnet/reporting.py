"""Simulation report generation (CSV + PDF).

These are human-readable artifacts for a completed simulation summary; they do
not perform any orbital computation themselves.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from satnet.domain.models import SimulationSummary


def _iso(timestamp: datetime) -> str:
    if timestamp.tzinfo is None:
        ts = timestamp.isoformat()
    else:
        ts = timestamp.astimezone(datetime.timezone.utc).isoformat()
    return ts


class ReportService:
    """Generate CSV and PDF exports for a SimulationSummary."""

    def csv_bytes(self, summary: SimulationSummary) -> bytes:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(
            [
                "Satellite A",
                "Satellite B",
                "TCA (UTC)",
                "Miss Distance (km)",
                "Relative Velocity (km/s)",
                "Pc",
                "Risk",
            ]
        )
        for e in summary.conjunctions:
            writer.writerow(
                [
                    e.satellite_a,
                    e.satellite_b,
                    _iso(e.tca),
                    f"{e.miss_distance_km:.6f}",
                    f"{e.relative_velocity_km_s:.6f}",
                    "N/A" if e.pc is None else f"{e.pc:.2e}",
                    e.risk_level.value,
                ]
            )
        return out.getvalue().encode("utf-8")

    def pdf_bytes(self, summary: SimulationSummary) -> bytes:
        out = io.BytesIO()
        doc = SimpleDocTemplate(out, pagesize=A4)
        styles = getSampleStyleSheet()

        story: list = [
            Paragraph("SatNet Simulation Report", styles["Title"]),
            Spacer(1, 12),
            Paragraph(
                f"Simulation: {summary.simulation_id}", styles["BodyText"]
            ),
            Paragraph(
                f"Satellites: {summary.satellite_count}  |  "
                f"Candidates: {summary.candidate_pairs}  |  "
                f"Conjunctions: {summary.conjunction_count}",
                styles["BodyText"],
            ),
            Spacer(1, 12),
        ]

        header = ["Pair", "TCA (UTC)", "Miss (km)", "Rel V (km/s)", "Pc", "Risk"]
        rows = [header]
        for e in summary.conjunctions:
            rows.append(
                [
                    f"{e.satellite_a} \u2194 {e.satellite_b}",
                    _iso(e.tca),
                    f"{e.miss_distance_km:.3f}",
                    f"{e.relative_velocity_km_s:.3f}",
                    "N/A" if e.pc is None else f"{e.pc:.2e}",
                    e.risk_level.value,
                ]
            )

        table = Table(rows, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#12243a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.append(table)
        doc.build(story)
        return out.getvalue()
