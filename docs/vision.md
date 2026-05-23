# Vision y Estrategia — chesslens

## Que es chesslens

Una lente para ver tu ajedrez con claridad. Analiza tus partidas de chess.com con Stockfish, detecta tus patrones reales, y genera un reporte narrativo mensual — como Spotify Wrapped pero para ajedrez.

## Core insight

chess.com tiene 150M+ usuarios registrados. El analisis de partidas con motor (el feature mas util para mejorar) esta detras de un paywall de $99/año en Diamond. El jugador casual de 1000-1600 ELO que quiere mejorar en serio no tiene una herramienta gratuita, narrativa y accionable.

## Diferenciacion

- **Wrapped mensual gratuito** — ningun servicio gratis genera un resumen narrativo tipo "este mes perdiste 5 partidas por timeout en el movimiento 18-22, eso te costo ~30 puntos de rating"
- **Puente diagnostico - estudio** — no solo estadisticas, sino "esta semana estudiá esta linea especifica en Lichess Practice"
- **AI-agnostico** — funciona con Claude, GPT-4, Gemini, o Ollama local (gratis). El tier gratuito puede usar Ollama.
- **Futuro: analisis ajustado al nivel del rival** — integracion con Maia (modelo entrenado con partidas humanas por ELO), no solo Stockfish que asume juego perfecto

## Modelo de negocio (tentativo)

- **Fase 1:** Personal, gratis, open source
- **Fase 2:** Freemium — gratis con Ollama, pago con Claude/GPT-4 ($3-5/mes)
- **Fase 3:** SaaS con hosting gestionado, sin setup

## Principios

1. **Usarlo uno mismo primero.** Si no lo usas cada semana, nadie lo usara.
2. **Funcional antes que bonito.** Un reporte que da informacion real vale mas que un dashboard perfecto.
3. **Un dolor a la vez.** Timeout y Francesa Exchange antes de cubrir todo el ajedrez.
4. **Privacy-first.** Los datos se quedan locales en fase 1. Sin analytics, sin tracking.
5. **AI como capa de presentacion, no de analisis.** Stockfish analiza, el LLM narra. No al reves.

## Competencia

| Herramienta | Precio | Diferencia |
|---|---|---|
| Chess Insights | $18/año | Dashboard + AI report narrativo, pero no Wrapped |
| Aimchess | $58/año | Plan semanal, recomendaciones poco accionables |
| FireChess | $5/mes | Analisis masivo con Stockfish en browser |
| Sensei Chess | Gratis | Analisis basico, sin narrativa profunda |
| chess.com Diamond | $99/año | Completo pero caro y paywalled |

El gap real: **reporte narrativo mensual gratuito + recomendaciones accionables especificas**.
