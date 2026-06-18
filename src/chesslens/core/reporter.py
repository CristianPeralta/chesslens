"""
LiteLLM narrative generator.
Takes a PatternReport and returns a structured text narrative.
"""
from __future__ import annotations

from litellm import completion

from chesslens.config import settings
from chesslens.core.patterns import PatternReport


_PAIN_CONTEXT = {
    "timeout": "The player frequently runs out of time. Focus recommendations on time management and game pacing.",
    "opening": "The player struggles with specific openings. Focus on opening preparation and early middle-game transitions.",
    "accuracy": "The player makes many positional inaccuracies. Focus on calculation habits and candidate move selection.",
    "blunders": "The player blunders frequently. Focus on blunder-check habits and tactical awareness.",
    "balanced": "The player has no dominant weakness. Provide balanced, improvement-oriented recommendations.",
}


def _build_prompt(report: PatternReport) -> str:
    worst_opening_info = (
        f"{report.worst_opening.name} ({report.worst_opening.games} games, "
        f"{report.worst_opening.win_rate:.0%} win rate)"
        if report.worst_opening
        else "N/A"
    )

    top_openings = (
        ", ".join(
            f"{o.name} ({o.games}g, {o.win_rate:.0%})"
            for o in report.top_openings[:3]
        )
        or "N/A"
    )

    avg_rating = None
    # ponytail: rating context derived from PatternReport fields available; no extra field needed
    pain_context = _PAIN_CONTEXT.get(report.main_pain, _PAIN_CONTEXT["balanced"])

    return f"""You are a personal chess coach generating a monthly improvement report.

Player: {report.username}
Month: {report.month}
Main weakness identified: {report.main_pain}
Coaching focus: {pain_context}

--- MONTHLY STATS ---
Total games: {report.total_games}
Record: {report.wins}W / {report.losses}L / {report.draws}D ({report.win_rate:.1%} win rate)
As White: {report.as_white.games} games, {report.as_white.win_rate:.1%} win rate
As Black: {report.as_black.games} games, {report.as_black.win_rate:.1%} win rate

Timeouts: {report.timeout_count} ({report.timeout_rate:.1%} of games)
{f"Average timeout ply: {report.avg_timeout_ply}" if report.avg_timeout_ply else ""}

Accuracy: {f"{report.avg_accuracy:.1f}%" if report.avg_accuracy else "N/A"}
Avg centipawn loss: {f"{report.avg_centipawn_loss:.1f}" if report.avg_centipawn_loss else "N/A"}
Blunders per game: {f"{report.blunders_per_game:.2f}" if report.blunders_per_game else "N/A"}

Top openings: {top_openings}
Worst opening: {worst_opening_info}

--- TAREA ---
Escribí un informe mensual de ajedrez en español neutro. Usá prosa fluida, sin headers, sin bullets, sin guiones, sin formato Markdown. Escribí como un entrenador real hablándole directamente al jugador.

El informe debe cubrir tres ideas en este orden, en párrafos separados:
1. Resumen del mes: 2-3 oraciones sobre el rendimiento general y la tendencia principal.
2. Patrón principal: 1-2 oraciones identificando lo que más está frenando al jugador, con un dato concreto de las estadísticas.
3. Tres recomendaciones: tres sugerencias específicas y accionables, escritas en prosa natural (no lista numerada). Cada una debe empezar con un verbo de acción. Ajustá el nivel según las stats del jugador.

Máximo 300 palabras. Tono cálido y directo.
"""


def generate_narrative(report: PatternReport) -> str:
    """Generate a narrative coaching report from a PatternReport."""
    response = completion(
        model=settings.model,
        messages=[{"role": "user", "content": _build_prompt(report)}],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()
