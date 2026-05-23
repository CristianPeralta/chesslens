# 0001 — LiteLLM como abstraccion de AI provider

**Status:** Accepted
**Date:** 2026-05-23

## Context

chesslens necesita un LLM para generar narrativa. Atarse a un solo provider (Anthropic, OpenAI) crea dependencia de precios, disponibilidad y politica de un tercero. En fase 3, el free tier deberia poder correr con Ollama local sin cambiar codigo.

## Decision

Usar LiteLLM como unica interfaz para llamadas a LLMs. El modelo se configura via variable de entorno `CHESSLENS_MODEL`.

## Consequences

- Cambiar de Claude a GPT-4 es una linea de `.env`
- Free tier con `ollama/llama3` es posible sin modificar core
- LiteLLM agrega una dependencia extra, pero es ampliamente mantenida y usada en produccion
- Cost tracking por llamada disponible via `litellm.completion` callbacks
